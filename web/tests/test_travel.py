from datetime import date

import httpx
import pytest

from app.templates_config import _short_date


def _trip(id=1, status="upcoming", tags=None, **kw):
    return {
        "id": id, "name": kw.get("name", "Example trip"), "start_date": "2026-12-17", "end_date": "2026-12-24",
        "travelers": kw.get("travelers"), "preferences": None, "checklist_note_id": None, "notes": kw.get("notes"),
        "default_tag_names": None, "tags": tags or [], "status": status,
        "cities": kw.get("cities", []), "countries": kw.get("countries", []),
        "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z",
    }


def _leg(id=1):
    return {
        "id": id, "trip_id": 1, "mode": "flight", "origin": "Alpha", "destination": "Beta", "origin_code": None,
        "destination_code": None, "departs_at": "2026-12-17T06:00:00Z", "arrives_at": "2026-12-17T09:00:00Z",
        "departs_tz": "UTC", "arrives_tz": "Europe/Stockholm", "departs_local": "2026-12-17T06:00:00",
        "arrives_local": "2026-12-17T10:00:00", "carrier": "XX", "number": "12", "booking_ref": "ABC123",
        "booking_url": None, "seat": "1A", "notes": None, "check_flight_url": "https://www.google.com/search?q=flight+XX+12",
    }


def _place(**kw):
    place = {"id": 3, "kind": "hotel", "name": "Hotel Example", "city": "Beta", "country": None, "maps_url": None,
             "lat": None, "lng": None, "address": None, "notes": None, "maps_link": "https://maps.example/x",
             "tags": [], "grade": None, "grade_count": 0}
    place.update(kw)
    return place


def _visit(id=11, status="planned", day="2026-12-18", grade=None, **kw):
    return {
        "id": id, "place_id": 3, "place": {"id": 3, "kind": "restaurant", "name": "Cafe Example", "city": "Beta",
                                          "maps_url": None, "lat": None, "lng": None, "maps_link": "https://maps.example/c"},
        "trip_id": 1, "trip_name": "Example trip", "status": status, "visit_date": day,
        "visit_time": kw.get("time", "20:00:00"), "notes": kw.get("notes"), "grade": grade,
    }


def _stay(id=7):
    return {
        "id": id, "trip_id": 1, "place_id": 3, "place": _place(), "check_in_at": "2026-12-17T14:00:00Z",
        "check_out_at": "2026-12-19T10:00:00Z", "timezone": "Europe/Stockholm",
        "check_in_local": "2026-12-17T15:00:00", "check_out_local": "2026-12-19T11:00:00",
        "booking_ref": None, "booking_url": None, "notes": None, "grade": 4,
    }


def _detail(**kw):
    detail = {
        **_trip(), "legs": [_leg()], "stays": [_stay()],
        "timeline": [
            {"kind": "leg", "at": "2026-12-17T06:00:00Z", "local": "2026-12-17T06:00:00", "timezone": "UTC",
             "title": "Alpha → Beta", "subtitle": "flight · XX 12", "ref_id": 1,
             "links": {"directions": "https://maps.example/dir", "check_flight": "https://example.com/flight"}},
            {"kind": "check_in", "at": "2026-12-17T14:00:00Z", "local": "2026-12-17T15:00:00",
             "timezone": "Europe/Stockholm", "title": "Check in: Hotel Example", "subtitle": "Beta", "ref_id": 7,
             "links": {"map": "https://maps.example/x", "cafes": "https://maps.example/c", "luggage": "https://maps.example/l"}},
        ],
        "warnings": [{"kind": "long_wait_before_check_in", "message": "Arrives 5 h before check-in", "leg_id": 1, "stay_id": 7}],
        "leave_home_at": None, "visits": [], "hidden_visit_count": 0,
    }
    detail.update(kw)
    return detail


def _route(mock_api, routes):
    # The checklist card on /travel reads this; most tests don't care about it.
    routes = {"/travel/checklist-template": [], "/travel/trips/1/other-events": [], "/travel/trips/1/forecast": None, "/travel/trips/1/while-away": None, "/travel/trips/1/unlinked-transactions": [], **routes}

    async def get(path, params=None):
        for prefix in sorted(routes, key=len, reverse=True):
            if path == prefix or path.startswith(prefix):
                value = routes[prefix]
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected GET {path}")

    mock_api["get"].side_effect = get


def _status_error(status, detail):
    request = httpx.Request("POST", "http://api/x")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(status, request=request, json={"detail": detail}))


def test_short_date():
    assert _short_date("2026-12-17") == "17 Dec 2026"
    assert _short_date("2026-12-17T10:00:00") == "17 Dec 2026"
    assert _short_date(None) == ""
    assert _short_date("garbage") == "garbage"


class TestTripsPage:
    def test_lists_trips_with_status_and_tags(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [_trip(tags=["Family"], travelers="Test travelers")], "/travel/tags": [{"id": 1, "name": "Family", "trip_count": 1}], "/travel/settings": None})
        html = client.get("/travel").text
        assert "Example trip" in html and "17 Dec 2026" in html and "upcoming" in html
        assert "Family" in html and 'href="/travel/1"' in html

    def test_trip_shows_its_cities_and_countries_below_the_title(self, client, mock_api):
        trip = _trip(cities=["Alpha", "Beta"], countries=["Examplia"])
        _route(mock_api, {"/travel/trips": [trip, _trip(id=2)], "/travel/tags": [], "/travel/settings": None})
        html = client.get("/travel/list").text
        assert html.count("data-trip-places") == 1
        assert "Alpha, Beta · Examplia" in html and html.index("Example trip") < html.index("Alpha, Beta")

    def test_city_and_country_filters_autocomplete_from_the_trip_locations(self, client, mock_api):
        _route(mock_api, {"/travel/trips/locations": {"cities": ["Alpha", "Beta"], "countries": ["Examplia"]},
                          "/travel/trips": [], "/travel/tags": [], "/travel/settings": None})
        html = client.get("/travel").text
        assert 'name="city" value="" list="city-options"' in html and 'name="country" value="" list="country-options"' in html
        assert '<option value="Alpha">' in html and '<option value="Examplia">' in html

    def test_filters_still_render_when_locations_are_unavailable(self, client, mock_api):
        _route(mock_api, {"/travel/trips/locations": _status_error(500, "x"), "/travel/trips": [], "/travel/tags": [],
                          "/travel/settings": None})
        assert 'id="city-options"' in client.get("/travel").text

    def test_default_filter_is_current_and_page_size_plus_one(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": None})
        client.get("/travel")
        params = dict(mock_api["get"].await_args_list[0].kwargs["params"])
        assert params["status"] == "current" and params["limit"] == 21

    def test_filters_are_forwarded(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": None})
        client.get("/travel/list?status=past&tag=Family&tag=Work&q=ex&date_from=2026-01-01")
        params = mock_api["get"].await_args_list[0].kwargs["params"]
        assert ("status", "past") in params and ("tag", "Family") in params and ("tag", "Work") in params
        assert ("q", "ex") in params and ("date_from", "2026-01-01") in params

    def test_unknown_status_falls_back_to_current(self, client, mock_api):
        _route(mock_api, {"/travel/trips": []})
        client.get("/travel/list?status=bogus")
        assert ("status", "current") in mock_api["get"].await_args_list[0].kwargs["params"]

    def test_pagination_next_keeps_filters(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [_trip(id=i) for i in range(1, 23)]})
        html = client.get("/travel/list?status=all&tag=Family").text
        assert html.count('id="trip-') == 20
        assert "offset=20" in html and "tag=Family" in html and "Previous" not in html

    def test_second_page_has_previous(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [_trip()]})
        html = client.get("/travel/list?offset=20").text
        assert "Previous" in html and "offset=0" in html

    def test_empty_state(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": None})
        assert "No trips match" in client.get("/travel").text

    def test_backend_down(self, client, mock_api):
        _route(mock_api, {"/travel": httpx.ConnectError("down")})
        resp = client.get("/travel")
        assert resp.status_code == 200 and "unavailable" in resp.text

    def test_requires_login(self, anon_client):
        assert anon_client.get("/travel", follow_redirects=False).status_code == 302

    def test_nav_link_present(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": None})
        assert 'href="/travel"' in client.get("/travel").text


class TestTripPage:
    def test_renders_timeline_warnings_legs_and_stays(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": [_place()]})
        html = client.get("/travel/1").text
        assert "Alpha → Beta" in html and "Check in: Hotel Example" in html
        assert "Arrives 5 h before check-in" in html
        assert "06:00" in html and "15:00" in html
        assert "Check flight" in html and "Cafes nearby" in html and "Luggage storage" in html
        assert "Ref ABC123" in html and "Grade 4/5" in html

    def test_stay_card_links_to_the_places_map(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": [_place()]})
        html = client.get("/travel/1").text
        stay_card = html[html.index('id="stay-'):]
        assert 'href="https://maps.example/x"' in stay_card[: stay_card.index("Edit")]

    def test_timeline_rows_with_warnings_are_highlighted(self, client, mock_api):
        detail = _detail()
        detail["timeline"][0]["warnings"] = ["Arrives 5 h before check-in"]
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": detail, "/travel/places": []})
        html = client.get("/travel/1").text
        # the timeline row plus the leg and stay the default warning points at
        assert html.count("data-warning-row") == 3

    def test_travelers_is_a_textarea_shown_on_its_own_lines(self, client, mock_api):
        detail = _detail()
        detail["travelers"] = "Ana, 34, partner\nLeo, 5, son"
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": detail, "/travel/places": []})
        html = client.get("/travel/1").text
        assert '<textarea name="travelers"' in html and "Leo, 5, son" in html

    def test_trip_page_offers_the_map_download(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        html = client.get("/travel/1").text
        assert 'href="/travel/1/map.csv"' in html and 'href="/travel/1/map.csv?scope=visited"' in html
        assert 'href="/travel/1/map.csv?scope=planned"' in html and 'href="/travel/1/map.csv?scope=missed"' in html

    def test_long_timeline_is_cut_with_a_link_to_the_full_page(self, client, mock_api):
        detail = _detail()
        detail["timeline"] = [
            {**detail["timeline"][0], "title": f"Step {n}", "local": f"2026-12-{10 + n:02d}T06:00:00"} for n in range(12)
        ]
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": detail, "/travel/places": []})
        html = client.get("/travel/1").text
        assert "Step 7" in html and "Step 8" not in html
        assert 'href="/travel/1/timeline"' in html and "See all 12 steps" in html

    @pytest.mark.parametrize("path", ["/travel/1", "/travel/1/timeline"])
    def test_timeline_highlights_todays_day(self, client, mock_api, monkeypatch, path):
        detail = _detail()
        detail["timeline"][0]["local"] = "2026-12-17T06:00:00"
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": detail, "/travel/places": []})
        monkeypatch.setattr("app.routes.travel.local_today", lambda: date(2026, 12, 17))
        assert client.get(path).text.count("data-today-row") == 1
        monkeypatch.setattr("app.routes.travel.local_today", lambda: date(2026, 12, 16))
        assert "data-today-row" not in client.get(path).text

    def test_while_away_and_ideas_cards_show_an_empty_state(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        html = client.get("/travel/1").text
        assert 'id="while-away"' in html and "No birthdays, tasks or recurring charges" in html
        assert 'id="ideas"' in html and "No ideas left to plan" in html

    def test_short_timeline_has_no_see_all_link(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        assert "See all" not in client.get("/travel/1").text

    def test_timeline_page_lists_every_step(self, client, mock_api):
        detail = _detail()
        detail["timeline"] = [
            {**detail["timeline"][0], "title": f"Step {n}", "local": f"2026-12-{10 + n:02d}T06:00:00"} for n in range(12)
        ]
        _route(mock_api, {"/travel/trips/1": detail})
        html = client.get("/travel/1/timeline").text
        assert "Step 0" in html and "Step 11" in html and "See all" not in html

    def test_timeline_page_for_unknown_trip_redirects(self, client, mock_api):
        _route(mock_api, {"/travel/trips/9": None})
        resp = client.get("/travel/9/timeline", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/travel"

    def test_groups_timeline_by_local_day(self, client, mock_api):
        detail = _detail()
        detail["timeline"][1]["local"] = "2026-12-18T09:00:00"
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": detail, "/travel/places": []})
        html = client.get("/travel/1").text
        assert "17 Dec 2026" in html and "18 Dec 2026" in html

    def test_no_warnings_block_when_clean(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(warnings=[]), "/travel/places": []})
        assert 'id="warnings"' not in client.get("/travel/1").text

    def test_empty_trip_explains_what_to_add(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(legs=[], stays=[], timeline=[], warnings=[]), "/travel/places": []})
        assert "Nothing booked yet" in client.get("/travel/1").text

    def test_unknown_trip_redirects_to_the_list(self, client, mock_api):
        _route(mock_api, {"/travel/trips/9": httpx.HTTPStatusError("x", request=httpx.Request("GET", "http://a"), response=httpx.Response(404))})
        resp = client.get("/travel/9", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/travel"

    def test_stay_form_offers_known_hotels(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": [_place()]})
        assert 'value="3"' in client.get("/travel/1").text


class TestWrites:
    @pytest.mark.parametrize("path,api_path", [("/travel/trips", "/travel/trips"), ("/travel/legs", "/travel/legs"),
                                               ("/travel/stays", "/travel/stays"), ("/travel/places", "/travel/places")])
    def test_post_is_proxied(self, client, mock_api, path, api_path):
        mock_api["post"].return_value = {"id": 5}
        resp = client.post(path, json={"name": "x"})
        assert resp.status_code == 200 and resp.json() == {"id": 5}
        mock_api["post"].assert_awaited_once_with(api_path, json={"name": "x"})

    @pytest.mark.parametrize("kind", ["trips", "legs", "stays"])
    def test_patch_is_proxied(self, client, mock_api, kind):
        mock_api["patch"].return_value = {"id": 5}
        assert client.patch(f"/travel/{kind}/5", json={"notes": "n"}).status_code == 200
        mock_api["patch"].assert_awaited_once_with(f"/travel/{kind}/5", json={"notes": "n"})

    @pytest.mark.parametrize("kind", ["trips", "legs", "stays"])
    def test_delete_is_proxied(self, client, mock_api, kind):
        mock_api["delete"].return_value = None
        assert client.delete(f"/travel/{kind}/5").status_code == 200
        mock_api["delete"].assert_awaited_once_with(f"/travel/{kind}/5")

    def test_backend_error_message_is_relayed(self, client, mock_api):
        mock_api["post"].side_effect = _status_error(422, "arrives_at cannot be before departs_at")
        resp = client.post("/travel/legs", json={})
        assert resp.status_code == 422 and resp.json() == {"error": "arrives_at cannot be before departs_at"}

    def test_unreachable_backend_is_502(self, client, mock_api):
        mock_api["post"].side_effect = httpx.ConnectError("down")
        assert client.post("/travel/trips", json={}).status_code == 502


class TestSettings:
    def test_page_shows_the_reminder_settings(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": {"airport_buffer_min": 150, "home_to_airport_min": 40}})
        html = client.get("/travel").text
        assert 'name="airport_buffer_min"' in html and 'value="150"' in html and 'value="40"' in html

    def test_page_works_when_settings_are_unavailable(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": httpx.ConnectError("down")})
        resp = client.get("/travel")
        assert resp.status_code == 200 and 'name="airport_buffer_min"' not in resp.text

    def test_put_is_proxied(self, client, mock_api):
        mock_api["put"].return_value = {"airport_buffer_min": 90, "home_to_airport_min": 40}
        resp = client.put("/travel/settings", json={"airport_buffer_min": 90})
        assert resp.status_code == 200
        mock_api["put"].assert_awaited_once_with("/travel/settings", json={"airport_buffer_min": 90})


def test_timeline_shows_the_leave_home_item(client, mock_api):
    detail = _detail()
    detail["timeline"].insert(0, {
        "kind": "leave_home", "at": "2026-12-17T03:00:00Z", "local": "2026-12-17T03:00:00", "timezone": "UTC",
        "title": "Leave home for the airport", "subtitle": "Alpha → Beta", "ref_id": 1, "links": {},
    })
    _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": detail, "/travel/places": []})
    html = client.get("/travel/1").text
    assert "Leave home for the airport" in html and "ti-door-exit" in html


class TestItinerary:
    def test_visits_are_grouped_by_day_with_undated_last(self, client, mock_api):
        visits = [_visit(id=1, day="2026-12-18"), _visit(id=2, day="2026-12-19", status="visited", grade=4), _visit(id=3, day=None, time=None)]
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(visits=visits), "/travel/places": [_place()]})
        html = client.get("/travel/1").text
        assert html.index("18 Dec 2026") < html.index("19 Dec 2026") < html.index("No day yet")
        assert "Cafe Example" in html and "20:00" in html and "4/5" in html

    def test_planned_visit_offers_visited_and_missed(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(visits=[_visit()]), "/travel/places": []})
        html = client.get("/travel/1").text
        assert 'data-status="visited"' in html and 'data-status="missed"' in html

    def test_visited_visit_offers_no_status_shortcuts(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(visits=[_visit(status="visited", grade=5)]), "/travel/places": []})
        assert 'class="btn btn-xs btn-ghost mark-visit"' not in client.get("/travel/1").text

    def test_empty_itinerary_explains_itself(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        assert "Nothing planned" in client.get("/travel/1").text

    def test_hidden_visits_offer_a_toggle(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(hidden_visit_count=3), "/travel/places": []})
        html = client.get("/travel/1").text
        assert "Show 3 planned/missed" in html and "all_visits=1" in html

    def test_toggle_asks_the_backend_for_everything(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(status="past"), "/travel/places": []})
        html = client.get("/travel/1?all_visits=1").text
        assert mock_api["get"].await_args_list[0].kwargs["params"] == {"all_visits": "true"}
        assert "Hide planned/missed" in html

    def test_visit_dialog_offers_known_places(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": [_place(id=9, name="Museum Example", kind="museum")]})
        html = client.get("/travel/1").text
        assert 'id="visit-dialog"' in html and "Museum Example" in html and 'name="place_kind"' in html


class TestPlacesPage:
    def test_city_and_country_filters_autocomplete_from_the_place_locations(self, client, mock_api):
        _route(mock_api, {"/travel/places/locations": {"cities": ["Alpha"], "countries": ["Examplia"]},
                          "/travel/places": [], "/travel/tags": []})
        html = client.get("/travel/places").text
        assert 'list="city-options"' in html and 'list="country-options"' in html
        assert '<option value="Alpha">' in html and '<option value="Examplia">' in html

    def test_lists_places_with_grade_and_tags(self, client, mock_api):
        _route(mock_api, {"/travel/places": [_place(tags=["Would return"], grade=4.5, grade_count=2)], "/travel/tags": [{"id": 1, "name": "Would return", "trip_count": 0, "place_count": 1}]})
        html = client.get("/travel/places").text
        assert "Hotel Example" in html and "4.5/5" in html and "Would return" in html and 'href="/travel/places/3"' in html

    def test_filters_are_forwarded(self, client, mock_api):
        _route(mock_api, {"/travel/places": []})
        client.get("/travel/places/list?kind=cafe&city=Lisbon&country=Portugal&tag=A&tag=B&min_grade=4&status=visited&no_trip=1&q=x")
        params = mock_api["get"].await_args_list[0].kwargs["params"]
        for pair in [("kind", "cafe"), ("city", "Lisbon"), ("country", "Portugal"), ("tag", "A"), ("tag", "B"),
                     ("min_grade", "4"), ("status", "visited"), ("no_trip", "true"), ("q", "x"), ("limit", 21)]:
            assert pair in params

    def test_bad_filter_values_are_ignored(self, client, mock_api):
        _route(mock_api, {"/travel/places": []})
        client.get("/travel/places/list?kind=spaceship&min_grade=9&status=maybe")
        keys = [k for k, _ in mock_api["get"].await_args_list[0].kwargs["params"]]
        assert "kind" not in keys and "min_grade" not in keys and "status" not in keys

    def test_pagination_keeps_filters(self, client, mock_api):
        _route(mock_api, {"/travel/places": [_place(id=i) for i in range(1, 23)]})
        html = client.get("/travel/places/list?kind=hotel&no_trip=1").text
        assert html.count('id="place-') == 20 and "offset=20" in html and "kind=hotel" in html and "no_trip=1" in html

    def test_empty_and_backend_down(self, client, mock_api):
        _route(mock_api, {"/travel/places": [], "/travel/tags": []})
        assert "No places match" in client.get("/travel/places").text
        _route(mock_api, {"/travel/places": httpx.ConnectError("down"), "/travel/tags": []})
        assert "unavailable" in client.get("/travel/places").text

    def test_places_route_is_not_taken_for_a_trip_id(self, client, mock_api):
        _route(mock_api, {"/travel/places": [], "/travel/tags": []})
        assert client.get("/travel/places").status_code == 200


class TestPlacePage:
    def _detail(self, **kw):
        return _place(
            tags=["Would return"], grade=4.0, grade_count=2, notes="Book the terrace", lat=38.7, lng=-9.1,
            visits=[_visit(id=1, status="visited", grade=4), _visit(id=2, status="planned", day=None)],
            stays=[{"id": 7, "trip_id": 1, "check_in_local": "2026-12-17T15:00:00", "check_out_local": "2026-12-19T11:00:00",
                    "grade": 4, "notes": "Quiet room"}], **kw,
        )

    def test_shows_derived_grade_history_and_stays(self, client, mock_api):
        _route(mock_api, {"/travel/places/3/costs": None, "/travel/places/3": self._detail()})
        html = client.get("/travel/places/3").text
        assert "4/5" in html and "2 grades" in html
        assert "Book the terrace" in html and "Quiet room" in html
        assert 'id="visit-1"' in html and 'id="visit-2"' in html
        assert 'href="/travel/1"' in html

    def test_edit_form_is_prefilled(self, client, mock_api):
        _route(mock_api, {"/travel/places/3/costs": None, "/travel/places/3": self._detail()})
        html = client.get("/travel/places/3").text
        assert 'value="38.7"' in html and 'value="Would return"' in html

    def test_visit_dialog_has_no_place_picker(self, client, mock_api):
        _route(mock_api, {"/travel/places/3/costs": None, "/travel/places/3": self._detail()})
        html = client.get("/travel/places/3").text
        assert 'id="visit-dialog"' in html and 'name="place_id"' not in html

    def test_unknown_place_redirects_to_the_list(self, client, mock_api):
        _route(mock_api, {"/travel/places/9": httpx.HTTPStatusError("x", request=httpx.Request("GET", "http://a"), response=httpx.Response(404))})
        resp = client.get("/travel/places/9", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/travel/places"


class TestVisitAndPlaceWrites:
    def test_visit_post_patch_delete_are_proxied(self, client, mock_api):
        mock_api["post"].return_value = {"id": 1}
        mock_api["patch"].return_value = {"id": 1}
        mock_api["delete"].return_value = None
        assert client.post("/travel/visits", json={"place_id": 3}).status_code == 200
        assert client.patch("/travel/visits/1", json={"status": "visited"}).status_code == 200
        assert client.delete("/travel/visits/1").status_code == 200
        mock_api["post"].assert_awaited_once_with("/travel/visits", json={"place_id": 3})
        mock_api["patch"].assert_awaited_once_with("/travel/visits/1", json={"status": "visited"})
        mock_api["delete"].assert_awaited_once_with("/travel/visits/1")

    def test_place_patch_and_delete_are_proxied(self, client, mock_api):
        mock_api["patch"].return_value = {"id": 3}
        mock_api["delete"].return_value = None
        assert client.patch("/travel/places/3", json={"notes": "n"}).status_code == 200
        assert client.delete("/travel/places/3").status_code == 200

    def test_place_in_use_message_is_relayed(self, client, mock_api):
        mock_api["delete"].side_effect = _status_error(409, "Place has visits or stays and can't be deleted")
        resp = client.delete("/travel/places/3")
        assert resp.status_code == 409 and "visits or stays" in resp.json()["error"]


def _cost(total="120.00", count=1, unconverted=0, **kw):
    return {"total_eur": total, "transaction_count": count, "unconverted_count": unconverted, **kw}


def _costs(**kw):
    costs = {
        "total": _cost("250.00", 3, 1),
        "by_kind": [{"kind": "flight", **_cost("120.00")}, {"kind": "lodging", **_cost("130.00", 2, 1)}],
        "legs": [{"id": 1, **_cost("120.00")}],
        "stays": [{"id": 7, **_cost("130.00", 2, 1)}],
        "visits": [{"id": 11, **_cost("35.50")}],
    }
    costs.update(kw)
    return costs


class TestCosts:
    def test_trip_page_shows_total_kinds_and_per_item_costs(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": _costs(), "/travel/trips/1": _detail(visits=[_visit()]), "/travel/places": []})
        html = client.get("/travel/1").text
        assert 'id="trip-costs"' in html and "250.00 €" in html and "each counted once" in html
        assert "1 without an EUR amount yet" in html
        assert "flight: <strong>120.00 €</strong>" in html and "lodging: <strong>130.00 €</strong>" in html
        assert "120.00 €" in html.split('id="leg-1"')[1].split("</div>")[0]
        assert "1 unconverted" in html.split('id="stay-7"')[1].split("</div>")[0]
        assert "35.50 €" in html.split('id="visit-11"')[1].split("</div>")[0]

    def test_no_cost_card_without_linked_transactions(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": _costs(total=_cost("0.00", 0), legs=[], stays=[], visits=[]),
                          "/travel/trips/1": _detail(), "/travel/places": []})
        assert 'id="trip-costs"' not in client.get("/travel/1").text

    def test_page_still_renders_when_costs_are_unavailable(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": httpx.ConnectError("down"), "/travel/trips/1": _detail(), "/travel/places": []})
        resp = client.get("/travel/1")
        assert resp.status_code == 200 and 'id="trip-costs"' not in resp.text

    def test_every_item_offers_the_transactions_dialog(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(visits=[_visit()]), "/travel/places": []})
        html = client.get("/travel/1").text
        for kind in ("legs", "stays", "visits"):
            assert f'data-kind="{kind}"' in html
        assert 'id="tx-dialog"' in html

    def test_place_page_shows_lifetime_cost(self, client, mock_api):
        place = _place(visits=[], stays=[])
        _route(mock_api, {"/travel/places/3/costs": {"total": _cost("80.00", 2)}, "/travel/places/3": place})
        assert "80.00 €" in client.get("/travel/places/3").text


class TestTransactionLinkProxies:
    def test_search_needs_a_query(self, client, mock_api):
        resp = client.get("/travel/transactions/search?q=")
        assert resp.json() == [] and not mock_api["get"].await_count

    def test_search_uses_the_finance_search(self, client, mock_api):
        mock_api["get"].return_value = [{"id": 9}]
        assert client.get("/travel/transactions/search?q=flight").json() == [{"id": 9}]
        mock_api["get"].assert_awaited_once_with("/finance/transactions", params={"search": "flight", "limit": 10})

    def test_search_backend_down(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        assert client.get("/travel/transactions/search?q=x").status_code == 502

    def test_list_link_unlink_are_proxied(self, client, mock_api):
        mock_api["get"].return_value = {"transactions": [], "cost": _cost("0.00", 0)}
        mock_api["post"].return_value = {"transactions": [], "cost": _cost()}
        mock_api["delete"].return_value = None
        assert client.get("/travel/links/legs/4").status_code == 200
        assert client.post("/travel/links/stays/4", json={"transaction_id": 9}).status_code == 200
        assert client.delete("/travel/links/visits/4/9").status_code == 200
        mock_api["get"].assert_awaited_once_with("/travel/legs/4/transactions")
        mock_api["post"].assert_awaited_once_with("/travel/stays/4/transactions", json={"transaction_id": 9})
        mock_api["delete"].assert_awaited_once_with("/travel/visits/4/transactions/9")

    def test_unknown_link_kind_never_reaches_the_backend(self, client, mock_api):
        assert client.get("/travel/links/trips/4").status_code == 404
        assert not mock_api["get"].await_count

    def test_transfer_refusal_is_relayed(self, client, mock_api):
        mock_api["post"].side_effect = _status_error(422, "Transfers can't be linked to a trip")
        resp = client.post("/travel/links/legs/4", json={"transaction_id": 9})
        assert resp.status_code == 422 and "Transfers" in resp.json()["error"]


class TestDefaultTagsAndCalendarImport:
    def test_apply_default_tags_is_proxied(self, client, mock_api):
        mock_api["post"].return_value = {"tags": ["Travel"], "added": 3}
        assert client.post("/travel/trips/1/apply-default-tags").json() == {"tags": ["Travel"], "added": 3}
        mock_api["post"].assert_awaited_once_with("/travel/trips/1/apply-default-tags")

    def test_apply_button_only_when_the_trip_has_default_tags(self, client, mock_api):
        routes = {"/travel/trips/1/costs": None, "/travel/places": []}
        _route(mock_api, {**routes, "/travel/trips/1": _detail()})
        assert 'id="apply-tags"' not in client.get("/travel/1").text
        _route(mock_api, {**routes, "/travel/trips/1": _detail(default_tag_names="Travel, Hotel")})
        assert 'id="apply-tags"' in client.get("/travel/1").text

    def test_calendar_events_are_proxied(self, client, mock_api):
        mock_api["get"].return_value = [{"event_id": 1}]
        assert client.get("/travel/trips/1/calendar-events").json() == [{"event_id": 1}]
        mock_api["get"].assert_awaited_once_with("/travel/trips/1/calendar-events")

    def test_trip_page_has_the_import_button_and_dialog(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        html = client.get("/travel/1").text
        assert 'id="import-calendar"' in html and 'id="calendar-dialog"' in html


def _recap(**kw):
    recap = {
        "trip_id": 1, "name": "Example trip", "start_date": "2031-12-17", "end_date": "2031-12-24", "status": "past", "days": 8,
        "leg_count": 2, "stay_count": 1, "visits_visited": 3, "visits_missed": 1, "visits_planned": 2,
        "cities": ["Lisbon", "Porto"], "countries": ["Portugal"],
        "spend": _cost("250.00", 3, 1), "spend_by_kind": [{"kind": "flight", **_cost("120.00")}],
        "to_complete": [
            {"kind": "visit", "id": 11, "place_id": 31, "place_name": "Cafe Example", "day": "2031-12-19", "missing": ["grade", "notes"]},
            {"kind": "stay", "id": 7, "place_id": 3, "place_name": "Hotel Example", "day": None, "missing": ["grade"]},
        ],
        "highlights": [{"kind": "visit", "id": 12, "place_id": 32, "place_name": "Museum Example", "grade": 5}],
    }
    recap.update(kw)
    return recap


class TestRecapPage:
    def test_shows_numbers_highlights_and_what_is_left(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/recap": _recap()})
        html = client.get("/travel/1/recap").text
        assert "250.00 €" in html and "1 not in EUR yet" in html and "8 days" in html
        assert "Lisbon, Porto" in html and "Portugal" in html and "flight: <strong>120.00 €</strong>" in html
        assert "1 missed · 2 never done" in html
        assert "Museum Example" in html and "5/5" in html
        assert "grade and notes missing" in html and "grade missing" in html and 'href="/travel/places/31"' in html

    def test_each_missing_item_links_to_its_edit_dialog_on_the_trip_page(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/recap": _recap()})
        html = client.get("/travel/1/recap").text
        assert "/travel/1?all_visits=1&amp;edit=visit-11&amp;back=/travel/1/recap" in html or "edit=visit-11&back=/travel/1/recap" in html
        assert "edit=stay-7" in html

    def test_nothing_left_to_write_down(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/recap": _recap(to_complete=[], highlights=[])})
        html = client.get("/travel/1/recap").text
        assert "Every visit and stay has a grade and notes" in html and 'id="recap-highlights"' not in html

    def test_unfinished_trip_says_so(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/recap": _recap(status="upcoming")})
        assert "not finished yet" in client.get("/travel/1/recap").text

    def test_unknown_trip_goes_back_to_the_trip_page(self, client, mock_api):
        _route(mock_api, {"/travel/trips/9/recap": httpx.HTTPStatusError("x", request=httpx.Request("GET", "http://a"), response=httpx.Response(404))})
        resp = client.get("/travel/9/recap", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/travel/9"

    def test_trip_page_links_to_the_recap(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        assert 'href="/travel/1/recap"' in client.get("/travel/1").text


class TestSearchFilters:
    def test_trip_city_and_country_filters_are_forwarded(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [_trip()]})
        client.get("/travel/list?status=all&city=Lisbon&country=Portugal")
        params = mock_api["get"].await_args_list[0].kwargs["params"]
        assert ("city", "Lisbon") in params and ("country", "Portugal") in params

    def test_trip_pagination_keeps_city_and_country(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [_trip(id=i) for i in range(1, 23)]})
        html = client.get("/travel/list?city=Lisbon&country=Portugal").text
        assert "city=Lisbon" in html and "country=Portugal" in html and "offset=20" in html

    def test_trip_filter_inputs_are_prefilled(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": None})
        html = client.get("/travel?city=Lisbon&country=Portugal").text
        assert 'name="city" value="Lisbon"' in html and 'name="country" value="Portugal"' in html

    def test_places_can_be_filtered_to_ungraded(self, client, mock_api):
        _route(mock_api, {"/travel/places": []})
        client.get("/travel/places/list?ungraded=1&kind=cafe")
        params = mock_api["get"].await_args_list[0].kwargs["params"]
        assert ("ungraded", "true") in params and ("kind", "cafe") in params

    def test_places_ungraded_checkbox_and_pagination(self, client, mock_api):
        _route(mock_api, {"/travel/places": [_place(id=i) for i in range(1, 23)], "/travel/tags": []})
        assert 'name="ungraded"' in client.get("/travel/places").text
        assert "ungraded=1" in client.get("/travel/places/list?ungraded=1").text


class TestAirportPicker:
    def test_trip_page_loads_picker_script(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        html = client.get("/travel/1").text
        assert "/static/js/airport-input.js" in html and html.count("initTerminalInput({") == 2

    def test_airport_data_is_served_with_zones(self, client):
        rows = client.get("/static/js/airports.json").json()
        by_code = {row[0]: row for row in rows}
        assert by_code["OPO"][1] == "Porto" and by_code["OPO"][4] == "Europe/Lisbon"
        assert by_code["LHR"][4] == "Europe/London" and by_code["ARN"][4] == "Europe/Stockholm"
        assert all(len(row) == 5 and len(row[0]) == 3 and row[4] for row in rows)

    def test_station_data_is_served_with_zones_and_codes_that_fit_the_leg_column(self, client):
        rows = client.get("/static/js/stations.json").json()
        by_code = {row[0]: row for row in rows if row[0]}
        assert by_code["9430007"][1:4] == ["Lisboa Santa Apolónia", "PT", "Europe/Lisbon"]
        assert all(len(row) == 6 and len(row[0]) <= 8 and row[1] and len(row[2]) == 2 and "/" in row[3] for row in rows)

    def test_airport_rail_stations_and_stations_without_a_uic_code_are_listed(self, client):
        names = {row[1] for row in client.get("/static/js/stations.json").json()}
        assert {"Schiphol Airport", "Frankfurt (M) Flughafen Fernbf", "Lisboa Oriente"} <= names

    def test_place_forms_load_city_picker(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(), "/travel/places": []})
        html = client.get("/travel/1").text
        assert html.index("/static/js/airport-input.js") < html.index("/static/js/travel-visits.js")
        assert "initCityInput" in html and "initCityInput" in client.get("/static/js/airport-input.js").text


class TestTripMapDownload:
    def test_csv_has_one_row_per_pin(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/map": {"trip_id": 1, "name": "T", "points": [
            {"name": "Hotel Example", "address": "Hotel Example, Lisbon", "category": "lodging", "status": "visited", "description": "Stay 02 Mar"},
            {"name": "OPO airport", "address": "OPO airport", "category": "airport", "status": "planned", "description": None},
        ]}})
        resp = client.get("/travel/1/map.csv")
        assert resp.headers["content-type"].startswith("text/csv") and "attachment" in resp.headers["content-disposition"]
        lines = resp.text.strip().splitlines()
        assert lines[0] == "Name,Address,Category,Status,Description"
        assert lines[1] == 'Hotel Example,"Hotel Example, Lisbon",lodging,visited,Stay 02 Mar'
        assert lines[2] == "OPO airport,OPO airport,airport,planned,"
        assert "map.csv" in resp.headers["content-disposition"] and "visited" not in resp.headers["content-disposition"]

    def test_visited_scope_is_forwarded_and_named_in_the_file(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/map": {"trip_id": 1, "name": "T", "points": []}})
        resp = client.get("/travel/1/map.csv?scope=visited")
        assert mock_api["get"].await_args.kwargs["params"] == {"scope": "visited"}
        assert "map-visited.csv" in resp.headers["content-disposition"]

    def test_each_scope_is_forwarded_and_named_in_the_file(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/map": {"trip_id": 1, "name": "T", "points": []}})
        for scope in ("planned", "visited", "missed"):
            resp = client.get(f"/travel/1/map.csv?scope={scope}")
            assert mock_api["get"].await_args.kwargs["params"] == {"scope": scope}
            assert f"map-{scope}.csv" in resp.headers["content-disposition"]

    def test_unknown_scope_falls_back_to_all(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/map": {"trip_id": 1, "name": "T", "points": []}})
        client.get("/travel/1/map.csv?scope=whatever")
        assert mock_api["get"].await_args.kwargs["params"] == {"scope": "all"}

    def test_unknown_trip_redirects_to_the_trip_page(self, client, mock_api):
        _route(mock_api, {"/travel/trips/9/map": None})
        resp = client.get("/travel/9/map.csv", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/travel/9"


class TestChecklist:
    def test_card_groups_items_by_anchor_and_shows_the_meaning(self, client, mock_api):
        template = [
            {"anchor": "start", "name": "plug-adapter", "title": "plug adapter", "offset_days": -7},
            {"anchor": "end", "name": "send-photos", "title": "send photos", "offset_days": 3},
        ]
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": None, "/travel/checklist-template": template})
        html = client.get("/travel").text
        assert "Around departure" in html and "After the trip" in html
        assert "7 days before the start" in html and "3 days after the end" in html

    def test_card_survives_the_backend_being_down(self, client, mock_api):
        _route(mock_api, {"/travel/trips": [], "/travel/tags": [], "/travel/settings": None, "/travel/checklist-template": _status_error(500, "x")})
        assert client.get("/travel").status_code == 200

    def test_put_delete_and_generate_proxy_to_the_backend(self, client, mock_api):
        mock_api["put"].return_value = {"anchor": "end", "name": "x", "title": "x", "offset_days": 3}
        assert client.put("/travel/checklist-template/end/x", json={"offset_days": 3}).status_code == 200
        mock_api["put"].assert_awaited_with("/travel/checklist-template/end/x", json={"offset_days": 3})
        mock_api["delete"].return_value = None
        assert client.delete("/travel/checklist-template/end/x").status_code == 200
        mock_api["delete"].assert_awaited_with("/travel/checklist-template/end/x")
        mock_api["post"].return_value = {"created": ["a (T)"], "skipped": []}
        assert client.post("/travel/trips/1/checklist").json() == {"created": ["a (T)"], "skipped": []}

    def test_backend_conflict_message_is_relayed(self, client, mock_api):
        mock_api["put"].side_effect = _status_error(409, "'x' already exists under the other anchor")
        resp = client.put("/travel/checklist-template/end/x", json={"offset_days": 3})
        assert resp.status_code == 409 and "already exists" in resp.json()["error"]


class TestTimelineHomeOffset:
    def test_offset_and_sleep_hint_are_shown(self, client, mock_api):
        timeline = _detail()["timeline"]
        timeline[0].update(home_offset="-3h", sleep_hint="-3h behind home: expect jet lag, try to sleep on local time")
        _route(mock_api, {"/travel/trips/1": _detail(timeline=timeline), "/travel/trips/1/costs": None})
        html = client.get("/travel/1/timeline").text
        assert "(-3h vs home)" in html and "expect jet lag" in html


class TestIdeas:
    def test_ideas_card_lists_undated_places_by_city(self, client, mock_api):
        idea = _visit(21, day=None)
        idea["trip_id"] = None
        ideas = [{"city": "Beta", "visits": [idea]}]
        _route(mock_api, {"/travel/trips/1": _detail(ideas=ideas), "/travel/places": [], "/travel/trips/1/costs": None})
        html = client.get("/travel/1").text
        assert "Ideas to plan" in html and "Cafe Example" in html and "wishlist" in html and "Plan on day" in html

    def test_empty_state_without_ideas(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(ideas=[]), "/travel/places": [], "/travel/trips/1/costs": None})
        assert "No ideas left to plan" in client.get("/travel/1").text


class TestVisitEvents:
    def test_delete_forwards_the_event_choice(self, client, mock_api):
        mock_api["delete"].return_value = None
        assert client.delete("/travel/visits/5?delete_event=true").status_code == 200
        mock_api["delete"].assert_awaited_with("/travel/visits/5?delete_event=true")
        client.delete("/travel/visits/5")
        mock_api["delete"].assert_awaited_with("/travel/visits/5")

    def test_row_shows_the_event_icon_and_marks_the_delete_button(self, client, mock_api):
        visit = _visit(21)
        visit["calendar_event_id"] = 77
        _route(mock_api, {"/travel/trips/1": _detail(visits=[visit]), "/travel/places": [], "/travel/trips/1/costs": None})
        html = client.get("/travel/1").text
        assert "ti-calendar-event" in html and 'data-event="77"' in html


class TestTodayPage:
    def _today(self, **kw):
        item = {"kind": "leg", "at": "2026-12-18T10:00:00Z", "local": "2026-12-18T11:00:00", "timezone": "UTC",
                "title": "Beta → Gamma", "subtitle": "train", "ref_id": 1, "links": {"directions": "https://maps.example/d"}}
        today = {"trip_id": 1, "trip_name": "Example trip", "date": "2026-12-18", "timezone": "UTC",
                 "next_item": item, "minutes_until_next": 135, "visits": [_visit(11)], "to_mark": 1}
        today.update(kw)
        return today

    def test_shows_the_next_step_with_countdown_and_the_visits_to_mark(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/today": self._today()})
        html = client.get("/travel/1/today").text
        assert "Beta → Gamma" in html and "in 2 h 15 min" in html and "Cafe Example" in html
        assert "1 to mark" in html and "Visited" in html and "Transit" in html

    def test_empty_day(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/today": self._today(next_item=None, minutes_until_next=None, visits=[], to_mark=0)})
        html = client.get("/travel/1/today").text
        assert "Nothing left on the timeline" in html and "No visits planned for today" in html

    def test_unknown_trip_redirects(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1/today": _status_error(404, "Trip not found")})
        assert client.get("/travel/1/today", follow_redirects=False).status_code == 302

    def test_link_only_while_ongoing(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(status="ongoing"), "/travel/places": [], "/travel/trips/1/costs": None})
        assert "/travel/1/today" in client.get("/travel/1").text
        _route(mock_api, {"/travel/trips/1": _detail(status="upcoming"), "/travel/places": [], "/travel/trips/1/costs": None})
        assert "/travel/1/today" not in client.get("/travel/1").text


class TestWarningsPreview:
    def _warnings(self, n, kind="visit_without_stay"):
        return [{"kind": kind, "message": f"Warning {i}", "visit_id": i} for i in range(n)]

    def _events(self, n):
        return [{"event_id": i, "title": f"Event {i}", "start_datetime": "2026-12-18T07:00:00+00:00",
                 "end_datetime": "2026-12-18T08:00:00+00:00", "all_day": False, "recurring": False, "snoozed": False}
                for i in range(n)]

    def test_trip_page_shows_only_a_warnings_title_linking_to_the_full_page(self, client, mock_api):
        warnings = self._warnings(8) + self._warnings(2, "tight_connection")
        _route(mock_api, {"/travel/trips/1": _detail(warnings=warnings), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/other-events": self._events(7)})
        html = client.get("/travel/1").text
        assert 'id="warnings" href="/travel/1/warnings"' in html and "Warning 0" not in html
        assert "Worth a look" in html and "10 warnings" in html
        assert 'id="other-events" href="/travel/1/warnings#other-events"' in html and "Event 0" not in html
        assert "7 other calendar events during the trip" in html

    def test_warnings_page_lists_every_group_foldable(self, client, mock_api):
        warnings = self._warnings(8) + self._warnings(2, "tight_connection")
        _route(mock_api, {"/travel/trips/1": _detail(warnings=warnings), "/travel/trips/1/other-events": self._events(7)})
        html = client.get("/travel/1/warnings").text
        assert html.count("<details") == 3
        assert "Warning 7" in html and "Event 6" in html
        assert 'id="visit_without_stay"' in html and 'id="other-events"' in html

    def test_warnings_page_redirects_for_a_missing_trip(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": None})
        response = client.get("/travel/1/warnings", follow_redirects=False)
        assert response.status_code == 302 and response.headers["location"] == "/travel"


class TestUnlinkedPreview:
    def _charges(self, n):
        return [{"id": i, "date": "2026-12-18", "merchant": f"Shop {i}", "amount": "5.00", "currency": "EUR", "type": "expense"}
                for i in range(n)]

    def test_trip_page_shows_five_charges_and_a_link_to_the_rest(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/unlinked-transactions": self._charges(8)})
        html = client.get("/travel/1").text
        assert "Shop 4" in html and "Shop 5" not in html
        assert 'href="/travel/1/unlinked"' in html and "See all 8" in html

    def test_unlinked_page_lists_every_charge(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/trips/1/unlinked-transactions": self._charges(8)})
        html = client.get("/travel/1/unlinked").text
        assert "Shop 7" in html and html.count("data-unlinked=") == 8

    def test_charge_without_merchant_or_description_shows_the_bank_text(self, client, mock_api):
        charge = {"id": 1, "date": "2026-12-18", "merchant": None, "description": None,
                  "bank_description": "SOME SHOP 123", "amount": "5.00", "currency": "EUR", "type": "expense"}
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/trips/1/unlinked-transactions": [charge]})
        assert "SOME SHOP 123" in client.get("/travel/1/unlinked").text

    def test_unlinked_page_redirects_for_a_missing_trip(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": None})
        response = client.get("/travel/1/unlinked", follow_redirects=False)
        assert response.status_code == 302 and response.headers["location"] == "/travel"


class TestTransactionDetail:
    _tx = {"id": 9, "account_id": 2, "date": "2026-12-18T12:30:00", "amount": "42.50", "currency": "USD", "amount_eur": "39.10",
           "type": "expense", "category_id": 4, "merchant": "Some Shop", "description": "Souvenirs", "bank_description": "SOME SHOP 123",
           "note": "Gift", "tags": ["Travel"]}

    def test_detail_partial_shows_the_fields_with_account_and_category_names(self, client, mock_api):
        _route(mock_api, {"/finance/transactions/9": self._tx, "/finance/accounts": [{"id": 2, "name": "Test Account"}],
                          "/finance/categories": [{"id": 4, "name": "Shopping"}]})
        html = client.get("/travel/transactions/9/detail").text
        for expected in ("Some Shop", "Souvenirs", "SOME SHOP 123", "Gift", "Test Account", "Shopping", "42.50 USD", "39.10 EUR", "Travel"):
            assert expected in html

    def test_detail_fails_softly_when_the_transaction_is_missing(self, client, mock_api):
        _route(mock_api, {"/finance/transactions/9": None})
        response = client.get("/travel/transactions/9/detail")
        assert response.status_code == 502 and "Could not load" in response.text

    def test_unlinked_page_rows_have_a_details_link_and_the_modal(self, client, mock_api):
        charges = [{"id": 9, "date": "2026-12-18", "merchant": "Some Shop", "amount": "5.00", "currency": "EUR", "type": "expense"}]
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/trips/1/unlinked-transactions": charges})
        html = client.get("/travel/1/unlinked").text
        assert 'class="text-xs text-[#378ADD] hover:underline tx-detail" data-id="9"' in html and 'id="tx-detail-dialog"' in html


class TestWarnedRows:
    def test_legs_stays_and_visits_with_warnings_are_marked_with_their_messages(self, client, mock_api):
        detail = _detail(warnings=[
            {"kind": "leg_not_paid", "message": "Leg problem text", "leg_id": 1},
            {"kind": "stay_not_paid", "message": "Stay problem text", "stay_id": 7},
        ])
        _route(mock_api, {"/travel/trips/1": detail, "/travel/places": [], "/travel/trips/1/costs": None})
        html = client.get("/travel/1").text
        leg_row = html[html.index('id="leg-1"') - 200:html.index('id="leg-1"') + 400]
        assert "data-warning-row" in leg_row and "Leg problem text" in html
        stay_row = html[html.index('id="stay-7"') - 200:html.index('id="stay-7"') + 400]
        assert "data-warning-row" in stay_row and "Stay problem text" in html


class TestOtherEvents:
    def _events(self, snoozed):
        return [{"event_id": 5, "title": "Gym", "start_datetime": "2026-12-18T07:00:00+00:00",
                 "end_datetime": "2026-12-18T08:00:00+00:00", "all_day": False, "recurring": True, "snoozed": snoozed}]

    def test_trip_card_is_a_title_and_the_warnings_page_lists_the_events_and_snooze_state(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/other-events": self._events(True)})
        trip_html = client.get("/travel/1").text
        assert "1 other calendar event during the trip" in trip_html and "Gym" not in trip_html
        html = client.get("/travel/1/warnings").text
        assert "Gym" in html and "snoozed" in html

    def test_card_hints_at_the_setting_when_nothing_is_snoozed(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/other-events": self._events(False)})
        assert "Turn on snoozing" in client.get("/travel/1/warnings").text

    def test_recurring_events_get_a_checkbox_skip_button_and_bulk_bar_but_one_offs_do_not(self, client, mock_api):
        events = self._events(False) + [{"event_id": 6, "title": "Dentist", "start_datetime": "2026-12-19T09:00:00",
                                         "end_datetime": "2026-12-19T10:00:00", "all_day": False, "recurring": False, "snoozed": False}]
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/other-events": events})
        html = client.get("/travel/1/warnings").text
        gym = html[html.index('data-other-event="5"'):html.index('data-other-event="6"')]
        dentist = html[html.index('data-other-event="6"'):]
        assert 'data-date="2026-12-18"' in gym and "other-event-pick" in gym and "other-event-skip" in gym
        assert "other-event-pick" not in dentist.split("</div>")[0] and "other-event-skip" not in dentist.split("</div>")[0]
        assert 'id="other-skip-selected"' in html and 'id="other-select-all"' in html

    def test_no_bulk_bar_when_nothing_is_recurring(self, client, mock_api):
        events = [dict(self._events(False)[0], recurring=False)]
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/other-events": events})
        assert 'id="other-skip-selected"' not in client.get("/travel/1/warnings").text

    def test_no_card_without_events_or_when_the_endpoint_fails(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/other-events": _status_error(500, "x")})
        assert "other calendar event" not in client.get("/travel/1").text


class TestForecast:
    def _forecast(self, **kw):
        base = {"trip_id": 1, "mode": "forecast", "available": True, "message": None, "cities": [{
            "city": "Beta", "days": [
                {"date": "2026-12-17", "min_c": 1.2, "max_c": 5.6, "precip_mm": 0.0, "rain": False},
                {"date": "2026-12-18", "min_c": 0.0, "max_c": 3.0, "precip_mm": 4.2, "rain": True}]}]}
        base.update(kw)
        return base

    def test_card_shows_days_and_marks_rain(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/forecast": self._forecast()})
        html = client.get("/travel/1").text
        assert 'data-weather-day="2026-12-18"' in html and "4.2 mm" in html and "6°" in html

    def test_unavailable_weather_says_so_and_the_page_still_renders(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/forecast": self._forecast(available=False, cities=[], message="The weather service is not available")})
        assert "The weather service is not available" in client.get("/travel/1").text

    def test_no_card_for_a_finished_trip(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/forecast": self._forecast(mode="none", available=False)})
        assert 'id="forecast"' not in client.get("/travel/1").text


class TestWhileAway:
    def test_card_lists_the_three_kinds(self, client, mock_api):
        away = {"trip_id": 1, "birthdays": [{"contact_id": 1, "name": "Some Person", "date": "2026-12-20"}],
                "tasks": [{"task_id": 2, "title": "Renew insurance", "due": "2026-12-22"}],
                "charges": [{"recurring_id": 3, "merchant": "Streaming", "amount": "9.99", "currency": "EUR", "date": "2026-12-25"}]}
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/while-away": away})
        html = client.get("/travel/1").text
        assert "While you are away" in html and "Some Person" in html and "Renew insurance" in html and "9.99 EUR" in html

    def test_empty_state_when_nothing_happens(self, client, mock_api):
        away = {"trip_id": 1, "birthdays": [], "tasks": [], "charges": []}
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/while-away": away})
        assert "No birthdays, tasks or recurring charges" in client.get("/travel/1").text


class TestPrintPage:
    def test_day_by_day_with_flight_numbers_bookings_addresses_and_visits(self, client, mock_api):
        detail = _detail(visits=[_visit(11, day="2026-12-18", notes="Corner table")])
        detail["legs"][0]["booking_ref"] = "ABC123"
        detail["stays"][0]["place"]["address"] = "Rua Exemplo 1"
        detail["stays"][0]["booking_ref"] = "HTL789"
        _route(mock_api, {"/travel/trips/1": detail})
        html = client.get("/travel/1/print").text
        assert "XX 12" in html and "Booking ABC123" in html
        assert "Rua Exemplo 1" in html and "Booking HTL789" in html
        assert "Cafe Example" in html and "Corner table" in html and "20:00" in html
        assert "Save as PDF" in html

    def test_missed_visits_are_left_out_and_unknown_trip_redirects(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(visits=[_visit(11, status="missed")])})
        assert "Cafe Example" not in client.get("/travel/1/print").text
        _route(mock_api, {"/travel/trips/1": _status_error(404, "x")})
        assert client.get("/travel/1/print", follow_redirects=False).status_code == 302


class TestUnlinkedCharges:
    def test_lists_charges_with_the_trips_items_as_link_targets(self, client, mock_api):
        unlinked = [{"id": 31, "date": "2026-12-18T12:00:00", "merchant": "Some Shop", "description": None,
                     "type": "expense", "amount": "12.50", "currency": "EUR", "amount_eur": "12.50"}]
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None,
                          "/travel/trips/1/unlinked-transactions": unlinked})
        html = client.get("/travel/1").text
        assert "Charges not linked to anything" in html and "Some Shop" in html and "12.50 EUR" in html
        assert 'value="legs:' in html and 'value="stays:' in html

    def test_no_card_when_everything_is_linked(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [], "/travel/trips/1/costs": None})
        assert "Charges not linked" not in client.get("/travel/1").text


class TestMoveVisitsPortal:
    def test_proxy_relays_the_move(self, client, mock_api):
        mock_api["post"].return_value = {"moved": [11], "failed": []}
        body = {"from_date": "2026-12-18", "to_date": "2026-12-20"}
        assert client.post("/travel/trips/1/visits/move", json=body).json() == {"moved": [11], "failed": []}
        mock_api["post"].assert_awaited_with("/travel/trips/1/visits/move", json=body)

    def test_rainy_day_with_planned_visits_offers_the_move(self, client, mock_api):
        forecast = {"trip_id": 1, "mode": "forecast", "available": True, "message": None, "cities": [{"city": "Beta", "days": [
            {"date": "2026-12-18", "min_c": 1, "max_c": 3, "precip_mm": 5.0, "rain": True},
            {"date": "2026-12-19", "min_c": 1, "max_c": 3, "precip_mm": 6.0, "rain": True}]}]}
        _route(mock_api, {"/travel/trips/1": _detail(visits=[_visit(11, day="2026-12-18")]), "/travel/places": [],
                          "/travel/trips/1/costs": None, "/travel/trips/1/forecast": forecast})
        html = client.get("/travel/1").text
        assert html.count("move-day") >= 2 and 'data-from="2026-12-18"' in html and 'data-from="2026-12-19"' not in html


class TestEventLinksPortal:
    def _page(self, client, mock_api, visit, warnings=()):
        detail = _detail(visits=[visit], warnings=list(warnings))
        detail["legs"][0]["calendar_event_id"] = 5
        _route(mock_api, {"/travel/trips/1": detail, "/travel/places": [], "/travel/trips/1/costs": None})
        return client.get("/travel/1").text

    def test_unlinked_visit_without_event_offers_create_and_link(self, client, mock_api):
        visit = _visit(11)
        visit["calendar_event_id"] = None
        html = self._page(client, mock_api, visit, [{"kind": "no_calendar_event", "message": "m", "visit_id": 11}])
        assert 'data-action="create"' in html and 'class="btn btn-xs btn-ghost link-event" data-kind="visits"' in html

    def test_mismatch_offers_both_directions_and_unlink(self, client, mock_api):
        visit = _visit(11)
        visit["calendar_event_id"] = 77
        html = self._page(client, mock_api, visit, [{"kind": "linked_event_mismatch", "message": "m", "visit_id": 11}])
        assert 'data-action="update_event"' in html and 'data-action="update_visit"' in html and 'unlink-event" data-kind="visits"' in html

    def test_legs_show_unlink_when_linked_and_link_otherwise(self, client, mock_api):
        html = self._page(client, mock_api, _visit(11))
        assert 'unlink-event" data-kind="legs"' in html and 'link-event" data-kind="stays"' in html

    def test_place_page_rows_have_no_event_buttons(self, client, mock_api):
        from app.routes import travel  # noqa: F401  (the shared row include is used there without event_actions)
        visit = _visit(11)
        visit["calendar_event_id"] = 77
        _route(mock_api, {"/travel/places/3": {**_place(), "visits": [visit], "stays": [], "tags": [], "grade": None}, "/travel/places/3/costs": None})
        resp = client.get("/travel/places/3")
        assert "link-event" not in resp.text and "event-action" not in resp.text


class TestPlaceHistoryHint:
    def test_place_options_carry_grade_and_tags_for_the_dialogs(self, client, mock_api):
        place = _place()
        place.update(grade=4.5, grade_count=3, tags=["Would return"])
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [place], "/travel/trips/1/costs": None})
        html = client.get("/travel/1").text
        assert 'data-grade="4.5"' in html and 'data-count="3"' in html and 'data-tags="Would return"' in html
        assert 'id="visit-place-history"' in html and 'id="stay-place-history"' in html
        assert "/static/js/travel-place-history.js" in html


class TestEmptyDays:
    def test_days_without_visits_get_a_hint(self, client, mock_api):
        detail = _detail(visits=[_visit(11, day="2026-12-18")])
        detail.update(start_date="2026-12-17", end_date="2026-12-19", status="upcoming")
        _route(mock_api, {"/travel/trips/1": detail, "/travel/places": [], "/travel/trips/1/costs": None})
        html = client.get("/travel/1").text
        assert 'id="empty-days"' in html and "17 Dec 2026, 19 Dec 2026" in html

    def test_no_hint_for_a_past_trip_or_an_empty_itinerary(self, client, mock_api):
        past = _detail(visits=[_visit(11)])
        past.update(status="past")
        _route(mock_api, {"/travel/trips/1": past, "/travel/places": [], "/travel/trips/1/costs": None})
        assert 'id="empty-days"' not in client.get("/travel/1").text
        _route(mock_api, {"/travel/trips/1": _detail(visits=[]), "/travel/places": [], "/travel/trips/1/costs": None})
        assert 'id="empty-days"' not in client.get("/travel/1").text
