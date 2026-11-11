import httpx
import pytest

from app.templates_config import _short_date


def _trip(id=1, status="upcoming", tags=None, **kw):
    return {
        "id": id, "name": kw.get("name", "Example trip"), "start_date": "2026-12-17", "end_date": "2026-12-24",
        "travelers": kw.get("travelers"), "preferences": None, "checklist_note_id": None, "notes": kw.get("notes"),
        "default_tag_names": None, "tags": tags or [], "status": status,
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
        assert "/static/js/airport-input.js" in html and "initAirportInput" in html

    def test_airport_data_is_served_with_zones(self, client):
        rows = client.get("/static/js/airports.json").json()
        by_code = {row[0]: row for row in rows}
        assert by_code["OPO"][1] == "Porto" and by_code["OPO"][4] == "Europe/Lisbon"
        assert by_code["LHR"][4] == "Europe/London" and by_code["ARN"][4] == "Europe/Stockholm"
        assert all(len(row) == 5 and len(row[0]) == 3 and row[4] for row in rows)
