import re
from datetime import date

import httpx
import pytest

from app.routes.places import list_filters, list_query, list_request, week_rows
from app.shared.location_kinds import EVERYDAY_KINDS, EVERYDAY_PICK_KINDS, KIND_ICONS, KINDS, TRIP_KINDS, location_icon
from starlette.datastructures import QueryParams

_HOMETOWN = {"id": 15, "name": "Hometown", "country": {"id": 1, "name": "Testland", "code": "TL"}}
_GROCERIES = {"id": 1, "name": "groceries"}
_HOURS = {"mon": [["08:00", "13:00"], ["14:00", "20:00"]], "sun": [], "hol": []}
_NO_TRAVEL = {"tags": [], "grade": None, "grade_count": 0, "visits": [], "stays": []}


def _place(id=1, name="Market", kind="supermarket", everyday=True, **kw):
    base = {
        "id": id, "name": name, "kind": kind, "city": _HOMETOWN, "address": None, "maps_url": None, "opening_hours": None,
        "opening_hours_text": "", "notes": None, "active": True, "categories": [], "everyday": everyday,
        "latitude": None, "longitude": None, "maps_link": f"https://maps.example/{id}",
        "today": {"date": "2026-11-23", "hours": None, "holiday": None, "note": None, "open_now": None},
        "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z",
    }
    base.update(kw)
    return base


def _travel_place(id=1, name="Cafe Example", kind="cafe", **kw):
    base = {**_place(id, name, kind), "tags": [], "grade": None, "grade_count": 0, "last_visit": None}
    del base["everyday"], base["categories"]
    base.update(kw)
    return base


def _visit(id=11, status="visited", visit_date="2026-03-14", **kw):
    base = {"id": id, "place_id": 1, "place": _travel_place(), "trip_id": None, "trip_name": None, "status": status,
            "visit_date": visit_date, "visit_time": None, "notes": None, "grade": 4 if status == "visited" else None,
            "calendar_event_id": None}
    base.update(kw)
    return base


def _routes(place=None, travel=None, places=None, travel_list=None, categories=None, travel_times=None, events=None,
            homes=None, cities=None, links=None):
    def fake_get(path, params=None):
        if path == "/location/places":
            assert params == {"kind": "home"}
            return homes if homes is not None else []
        if path == "/location/cities":
            return cities if cities is not None else [_HOMETOWN]
        if path == "/organizer/calendar-events":
            return events if events is not None else []
        if path == "/organizer/places":
            return places if places is not None else []
        if path == "/travel/places":
            return travel_list if travel_list is not None else []
        if path == "/travel/tags":
            return [{"id": 1, "name": "family"}]
        if path == "/organizer/shopping-categories":
            return categories if categories is not None else [_GROCERIES]
        if path.endswith("/travel-times"):
            return travel_times if travel_times is not None else []
        if path.endswith("/costs"):
            return None
        if path.endswith("/links"):
            return links if links is not None and path.startswith("/travel/places/") else []
        if path.startswith("/organizer/places/"):
            if place is None:
                raise httpx.HTTPStatusError("404", request=httpx.Request("GET", path), response=httpx.Response(404))
            return place
        if path.startswith("/travel/places/"):
            if travel is None and place is None:
                raise httpx.HTTPStatusError("404", request=httpx.Request("GET", path), response=httpx.Response(404))
            return travel if travel is not None else _NO_TRAVEL
        raise AssertionError(path)

    return fake_get


@pytest.fixture
def monday(monkeypatch):
    monkeypatch.setattr("app.routes.places.local_today", lambda: date(2026, 11, 23))


class TestKinds:
    def test_every_kind_has_its_own_icon(self):
        assert len(set(KIND_ICONS.values())) == len(KINDS) == 24
        assert location_icon("work") == "ti-briefcase" and location_icon("hotel") == "ti-bed"

    def test_unknown_kind_falls_back_to_the_pin(self):
        assert location_icon("office") == "ti-map-pin"
        assert location_icon(None) == "ti-map-pin"

    def test_everyday_defaults_are_known_kinds(self):
        assert EVERYDAY_KINDS.isdisjoint(TRIP_KINDS) and (EVERYDAY_KINDS | TRIP_KINDS) <= set(KINDS)

    def test_calendar_picker_offers_no_home_and_no_trip_kinds(self):
        assert "home" not in EVERYDAY_PICK_KINDS and "hotel" not in EVERYDAY_PICK_KINDS and "cafe" in EVERYDAY_PICK_KINDS


class TestListHelpers:
    def test_week_rows_mark_today_and_unknown_days(self):
        rows = week_rows(_HOURS, "mon")

        assert rows[0] == {"label": "Monday", "hours": "08:00-13:00, 14:00-20:00", "today": True}
        assert rows[1]["hours"] == "unknown" and not rows[1]["today"]
        assert rows[6]["hours"] == "closed"
        assert rows[7] == {"label": "Public holidays", "hours": "closed", "today": False}

    def test_filters_default_to_the_everyday_view_and_drop_unknown_values(self):
        f = list_filters(QueryParams("view=nope&kind=castle&city_id=x&min_grade=9"))
        assert (f["view"], f["kind"], f["city_id"], f["min_grade"], f["archived"]) == ("everyday", "", "", "", False)

    def test_everyday_view_asks_the_everyday_api(self):
        f = list_filters(QueryParams("view=everyday&kind=pharmacy&q=school&city_id=15&tag=family"))
        path, params = list_request(f, 24)
        assert path == "/organizer/places"
        assert params == [("limit", 25), ("offset", 24), ("active", "true"), ("q", "school"), ("kind", "pharmacy"), ("city_id", "15")]

    def test_visited_view_asks_travel_for_places_with_visits(self):
        f = list_filters(QueryParams("view=visited&city_id=15&min_grade=4&tag=family&ungraded=1&archived=1"))
        path, params = list_request(f, 0)
        assert path == "/travel/places"
        assert ("has_visits", "true") in params and ("min_grade", "4") in params and ("tag", "family") in params
        assert ("ungraded", "true") in params and ("active", "true") not in params

    def test_all_view_lists_every_place_through_travel(self):
        path, params = list_request(list_filters(QueryParams("view=all")), 0)
        assert path == "/travel/places" and ("has_visits", "true") not in params

    def test_query_keeps_the_filters_for_pagination(self):
        f = list_filters(QueryParams("view=visited&q=x&tag=a&tag=b&archived=1"))
        assert list_query(f) == "view=visited&q=x&tag=a&tag=b&archived=1"


class TestListPage:
    def test_everyday_cards_show_status_hours_and_categories(self, client, mock_api):
        mock_api["get"].side_effect = _routes(places=[
            _place(1, "Home", "home", address="Rua A 1"),
            _place(2, "Market", opening_hours=_HOURS, categories=[_GROCERIES],
                   today={"date": "2026-11-23", "hours": "08:00-13:00, 14:00-20:00", "holiday": None, "note": None,
                          "open_now": True}),
        ])

        resp = client.get("/places")

        assert resp.status_code == 200
        assert "Home" in resp.text and "Rua A 1" in resp.text and "Open now" in resp.text
        assert "Today 08:00-13:00, 14:00-20:00" in resp.text
        assert 'href="/places/2"' in resp.text
        assert '<i class="ti ti-pill' not in resp.text and '<i class="ti ti-home text-sm" title="home"></i> Home' in resp.text

    def test_view_chips_and_nav(self, client, mock_api):
        mock_api["get"].side_effect = _routes()

        text = client.get("/places?view=visited").text

        assert re.search(r'href="/places\?view=visited" class="[^"]*bg-\[#378ADD\][^"]*" data-view="visited"', text)
        assert 'href="/places?view=everyday"' in text and 'href="/places?view=all"' in text
        assert '<a href="/places" class="nav-link active">' in text
        assert 'href="/places/cities"' in text and 'href="/places/countries"' in text  # the section's tabs

    def test_visited_rows_show_city_grade_last_visit_and_tags(self, client, mock_api):
        mock_api["get"].side_effect = _routes(travel_list=[
            _travel_place(3, grade=4.5, grade_count=2, tags=["would return"], last_visit="2026-03-14"),
        ])

        text = client.get("/places?view=visited").text

        assert 'href="/places/3"' in text and "4.5/5" in text and "would return" in text
        assert "last 14 Mar 2026" in text
        assert 'href="/places/cities/15"' in text
        assert 'name="min_grade"' in text and 'value="family"' in text

    def test_everyday_view_has_no_travel_filters(self, client, mock_api):
        mock_api["get"].side_effect = _routes()
        text = client.get("/places").text
        assert 'name="min_grade"' not in text and 'name="archived"' in text

    def test_city_filter_lists_the_cities(self, client, mock_api):
        mock_api["get"].side_effect = _routes()
        text = client.get("/places?city_id=15").text
        assert '<option value="15" selected>Hometown, Testland</option>' in text

    def test_partial_paginates(self, client, mock_api):
        mock_api["get"].side_effect = _routes(travel_list=[_travel_place(i, f"P{i}") for i in range(25)])

        text = client.get("/places/list?view=all&offset=24").text

        assert text.count('id="place-') == 24
        assert "/places/list?view=all&offset=0" in text and "/places/list?view=all&offset=48" in text

    def test_empty_and_unavailable(self, client, mock_api):
        mock_api["get"].side_effect = _routes(places=[])
        assert "No everyday places yet" in client.get("/places").text
        assert "No visited places yet" in client.get("/places?view=visited").text

        def failing(path, params=None):
            raise httpx.ConnectError("down")
        mock_api["get"].side_effect = failing
        assert "unavailable right now" in client.get("/places").text

    def test_new_form_starts_in_the_home_city_and_offers_every_kind(self, client, mock_api):
        mock_api["get"].side_effect = _routes(homes=[_place(29, "Home", "home")], categories=[_GROCERIES, {"id": 2, "name": "pharmacy"}])

        text = client.get("/places").text

        assert 'data-url="/places" data-method="POST"' in text
        assert '<input type="hidden" name="city_id" value="15">' in text and "the home city unless you pick another" in text
        assert '<option value="hotel">hotel</option>' in text and '<option value="other" selected>other</option>' in text
        assert "data-everyday-box" in text and 'name="category_ids" value="2"' in text
        assert 'data-everyday-kinds="bakery,' in text


@pytest.mark.usefixtures("monday")
class TestDetailPage:
    def test_everyday_place_shows_hours_sells_travel_times_and_events(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(
            address="Rua A 1", opening_hours=_HOURS, opening_hours_text="mon 08:00-13:00, 14:00-20:00; sun closed",
            categories=[_GROCERIES],
            today={"date": "2026-11-23", "hours": "08:00-13:00, 14:00-20:00", "holiday": None, "note": None, "open_now": True},
        ))

        resp = client.get("/places/1")

        assert resp.status_code == 200
        assert "data-today" in resp.text and "Monday" in resp.text and "Open now" in resp.text
        for card in ("place-hours", "place-sells", "place-travel-times", "place-events", "place-grade"):
            assert f'id="{card}"' in resp.text
        assert 'href="https://maps.example/1"' in resp.text
        assert 'name="category_ids" value="1" class="checkbox checkbox-xs"\n               checked' in resp.text
        assert "mon 08:00-13:00, 14:00-20:00\nsun closed</textarea>" in resp.text
        assert 'data-url="/places/1" data-method="PATCH"' in resp.text
        assert 'id="toggle-everyday" data-everyday="true"' in resp.text

    def test_trip_place_shows_grade_visits_stays_tags_and_links_but_no_everyday_cards(self, client, mock_api):
        stay = {"id": 4, "trip_id": 2, "check_in_local": "2026-03-10T15:00", "check_out_local": "2026-03-12T11:00",
                "grade": 5, "notes": None}
        travel = {"tags": ["would return"], "grade": 4.5, "grade_count": 2, "visits": [_visit(trip_id=2, trip_name="Spring")],
                  "stays": [stay]}
        mock_api["get"].side_effect = _routes(place=_place(3, "Hotel Example", "hotel", everyday=False), travel=travel,
                                              links=[{"id": 9, "trip_id": None, "place_id": 1, "url": "https://example.com", "kind": "website", "title": "Site", "description": None, "image_url": None, "notes": None, "created_at": "2026-11-15T00:00:00Z", "updated_at": "2026-11-15T00:00:00Z"}])

        text = client.get("/places/3").text

        for card in ("place-sells", "place-travel-times", "place-events", "place-hours"):
            assert f'id="{card}"' not in text
        assert 'id="visit-history"' in text and 'id="visit-11"' in text and 'id="stay-4"' in text
        assert "4.5/5" in text and 'id="place-tags"' in text and "would return" in text
        assert 'id="web-links"' in text and 'href="/travel/2"' in text
        assert 'id="toggle-everyday" data-everyday="false"' in text
        assert 'name="tags" value="would return"' in text
        assert 'name="category_ids"' not in text  # Sells is for everyday places
        mock_api["get"].assert_any_await("/travel/places/3", params=None)
        assert not [c for c in mock_api["get"].await_args_list if c.args[0].endswith("/travel-times")]

    @staticmethod
    def _columns(text):
        """The card ids of each column of the page's card layout, in order."""
        import re
        layout = text[text.index('id="place-cards"'):text.index('id="visit-dialog"') if 'id="visit-dialog"' in text else None]
        stacks = layout.split('<div class="card-stack">')[1:] or [layout]
        return [re.findall(r'<div class="card bg-white[^"]*" id="([a-z-]+)"', stack) for stack in stacks]

    def test_trip_place_has_grade_and_visits_left_the_rest_right(self, client, mock_api):
        stay = {"id": 4, "trip_id": 2, "check_in_local": "2026-03-10T15:00", "check_out_local": "2026-03-12T11:00",
                "grade": 5, "notes": None}
        travel = {"tags": ["view"], "grade": 4.5, "grade_count": 2, "visits": [], "stays": [stay]}
        mock_api["get"].side_effect = _routes(place=_place(3, "Hotel Example", "hotel", everyday=False, notes="Ask for a high floor"),
                                              travel=travel)

        text = client.get("/places/3").text

        assert '<div class="split" id="place-cards">' in text
        assert self._columns(text) == [["place-grade", "visit-history"], ["place-tags", "place-notes", "web-links"]]

    def test_trip_place_with_two_cards_is_one_column(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(3, "Sight Example", "attraction", everyday=False))

        text = client.get("/places/3").text

        assert '<div class="card-stack" id="place-cards">' in text and '<div class="split" id="place-cards">' not in text
        assert self._columns(text) == [["place-grade", "web-links"]]

    def test_everyday_place_keeps_its_two_columns(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(notes="Cash only"))

        text = client.get("/places/1").text

        assert 'id="place-cards"' not in text
        left = text[text.index('<div class="split">'):text.index('id="place-grade"')]
        assert 'id="place-sells"' in left and 'id="place-notes"' in left

    def test_grade_card_on_every_place_logs_a_visit_or_a_want_to_go(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place())

        text = client.get("/places/1").text

        assert 'id="log-visit"' in text and 'value="2026-11-23" max="2026-11-23"' in text
        assert '<button type="button" class="btn btn-sm btn-ghost" id="want-to-go">' in text
        assert "trip_from_date: true" in text and "Not graded yet" in text
        assert 'id="visit-history"' not in text

    def test_a_planned_undated_visit_means_already_wanted(self, client, mock_api):
        travel = {**_NO_TRAVEL, "visits": [_visit(status="planned", visit_date=None)]}
        mock_api["get"].side_effect = _routes(place=_place(), travel=travel)

        text = client.get("/places/1").text

        assert "On your want-to-go list" in text and '<button type="button" class="btn btn-sm btn-ghost" id="want-to-go">' not in text

    def test_visits_are_capped_with_a_link_to_the_full_page(self, client, mock_api):
        travel = {**_NO_TRAVEL, "visits": [_visit(i) for i in range(1, 8)]}
        mock_api["get"].side_effect = _routes(place=_place(), travel=travel)

        text = client.get("/places/1").text

        assert len(re.findall(r'id="visit-\d+"', text)) == 5
        assert 'href="/places/1/visits"' in text and "See all 7" in text

    def test_visits_page_lists_every_visit_and_stay(self, client, mock_api):
        travel = {**_travel_place(), "visits": [_visit(i) for i in range(1, 8)], "stays": []}
        mock_api["get"].side_effect = _routes(place=_place(), travel=travel)

        resp = client.get("/places/1/visits")

        assert resp.status_code == 200 and len(re.findall(r'id="visit-\d+"', resp.text)) == 7

    def test_home_is_always_everyday(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(kind="home", name="Home", address="Rua A 1"))

        text = client.get("/places/1").text

        assert 'id="toggle-everyday"' not in text and "Home is always an everyday place" in text
        assert 'data-home-address="Rua A 1" data-home-city="15"' in text
        assert "the home city: trips start here" in text and 'id="home-moved"' not in text

    def test_edit_form_has_the_kind_city_and_coordinates(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(kind="work", name="Office", latitude=41.1579, longitude=-8.6291))

        text = client.get("/places/1").text

        assert '<option value="work" selected>work</option>' in text
        assert 'name="coordinates" value="41.1579, -8.6291"' in text
        assert '<input type="hidden" name="city_id" value="15">' in text and '"name": "Hometown"' in text
        assert 'id="city-dialog"' in text and "/static/js/travel-city-picker.js" in text
        assert '<i class="ti ti-briefcase"></i> Office' in text

    def test_holiday_banner(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(
            opening_hours={"mon": [["08:00", "20:00"]]},
            today={"date": "2026-11-23", "hours": "08:00-20:00", "holiday": "Feriado", "note": "holiday, hours unknown",
                   "open_now": None},
        ))

        text = client.get("/places/1").text

        assert "Today is a public holiday (Feriado): holiday, hours unknown." in text
        assert "Open now" not in text and "Closed now" not in text

    def test_moved_banner_only_for_home(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(kind="home", name="Home"))
        assert 'id="home-moved"' in client.get("/places/1?moved=1").text

        mock_api["get"].side_effect = _routes(place=_place())
        text = client.get("/places/1?moved=1").text
        assert 'id="home-moved"' not in text and "data-home-address" not in text

    def test_unknown_hours(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place())
        assert "Hours unknown" in client.get("/places/1").text

    def test_missing_place_is_404(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=None)

        resp = client.get("/places/9")

        assert resp.status_code == 404 and "does not exist" in resp.text
        assert client.get("/places/9/visits").status_code == 404
        assert client.get("/places/9/links").status_code == 404

    def test_costs_link_to_the_charges_and_back_to_the_place(self, client, mock_api):
        travel = {**_NO_TRAVEL, "visits": [_visit(7, calendar_event_id=77)]}
        costs = {"total": {"total_eur": "80.00", "transaction_count": 2, "unconverted_count": 0},
                 "visits": [{"id": 7, "total_eur": "45.00", "transaction_count": 1, "unconverted_count": 0}]}
        routes = _routes(place=_place(name="Cafe Example", kind="cafe", everyday=False), travel=travel)
        mock_api["get"].side_effect = lambda path, params=None: costs if path == "/travel/places/1/costs" else routes(path, params)

        text = client.get("/places/1").text

        assert "80.00 €" in text and "45.00 €" in text
        assert 'href="/travel/charges?scope=place&id=1&name=Cafe%20Example&back=/places/1"' in text
        assert "link-event" not in text and "event-action" not in text  # event buttons are for the trip page

    def test_shows_its_citys_links_but_not_the_countrys(self, client, mock_api):
        city_link = {"id": 2, "trip_id": None, "place_id": None, "url": "https://city.example/", "kind": "website", "title": None,
                     "description": None, "image_url": None, "notes": None, "created_at": "2026-11-15T00:00:00Z", "updated_at": "2026-11-15T00:00:00Z"}
        routes = _routes(place=_place())
        mock_api["get"].side_effect = lambda path, params=None: [city_link] if path == "/travel/cities/15/links" else routes(path, params)

        text = client.get("/places/1").text

        assert "Links · Hometown" in text and "https://city.example/" in text
        assert all(c.args[0] != "/travel/countries/1/links" for c in mock_api["get"].await_args_list)

    def test_links_page(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(), links=[{"id": 9, "trip_id": None, "place_id": 1, "url": "https://example.com", "kind": "website", "title": "Site", "description": None, "image_url": None, "notes": None, "created_at": "2026-11-15T00:00:00Z", "updated_at": "2026-11-15T00:00:00Z"}])

        text = client.get("/places/1/links").text

        assert "https://example.com" in text and 'href="/places/1"' in text


class TestHomeLink:
    def test_opens_the_home_place(self, client, mock_api):
        mock_api["get"].side_effect = _routes(homes=[_place(29, "Home", "home")])
        response = client.get("/places/home", follow_redirects=False)
        assert (response.status_code, response.headers["location"]) == (302, "/places/29")

    def test_without_a_home_opens_the_list(self, client, mock_api):
        mock_api["get"].side_effect = _routes(homes=[])
        assert client.get("/places/home", follow_redirects=False).headers["location"] == "/places"


class TestRedirects:
    @pytest.mark.parametrize("old, new", [
        ("/locations", "/places"),
        ("/locations/7", "/places/7"),
        ("/locations/7/travel-times", "/places/7/travel-times"),
        ("/locations/home", "/places/home"),
        ("/travel/places", "/places?view=visited"),
        ("/travel/places/7", "/places/7"),
        ("/travel/places/7/links", "/places/7/links"),
    ])
    def test_old_urls_move_permanently(self, client, old, new):
        response = client.get(old, follow_redirects=False)
        assert (response.status_code, response.headers["location"]) == (301, new)


class TestWrites:
    def test_create_an_everyday_place_with_tags(self, client, mock_api):
        mock_api["post"].return_value = _place(id=5)

        body = {"name": "Market", "opening_hours": "mon 8-20", "everyday": True, "category_ids": [1], "tags": ["family"]}
        resp = client.post("/places", json=body)

        assert resp.status_code == 200 and resp.json() == {"id": 5}
        mock_api["post"].assert_awaited_once_with(
            "/organizer/places", json={"name": "Market", "opening_hours": "mon 8-20", "category_ids": [1]}
        )
        mock_api["patch"].assert_awaited_once_with("/travel/places/5", json={"tags": ["family"]})

    def test_create_a_place_that_is_not_everyday(self, client, mock_api):
        mock_api["post"].return_value = _place(id=6)

        client.post("/places", json={"name": "Museum", "kind": "museum", "everyday": False, "category_ids": [1], "tags": []})

        mock_api["post"].assert_awaited_once_with("/location/places", json={"name": "Museum", "kind": "museum"})
        mock_api["patch"].assert_not_awaited()

    def test_backend_error_message_is_relayed(self, client, mock_api):
        response = httpx.Response(422, json={"detail": "Opening hours: 'funday' is not a day"})
        mock_api["post"].side_effect = httpx.HTTPStatusError("422", request=httpx.Request("POST", "/"), response=response)

        resp = client.post("/places", json={"name": "Market", "opening_hours": "funday 9", "everyday": True})

        assert resp.status_code == 422 and resp.json() == {"error": "Opening hours: 'funday' is not a day"}

    def test_update_splits_the_fields_over_the_three_domains(self, client, mock_api):
        mock_api["get"].return_value = _place()

        response = client.patch("/places/1", json={"name": "Market", "category_ids": [2], "tags": ["family"]})

        assert response.status_code == 200
        assert mock_api["patch"].await_args_list[0].args == ("/location/places/1",)
        assert mock_api["patch"].await_args_list[0].kwargs == {"json": {"name": "Market"}}
        mock_api["put"].assert_awaited_once_with("/organizer/places/1/categories", json={"category_ids": [2]})
        assert mock_api["patch"].await_args_list[1].args == ("/travel/places/1",)
        mock_api["get"].assert_awaited_once_with("/organizer/places/1")

    def test_everyday_toggle(self, client, mock_api):
        mock_api["get"].return_value = _place()

        client.patch("/places/1", json={"everyday": True})
        mock_api["put"].assert_awaited_once_with("/organizer/places/1")
        client.patch("/places/1", json={"everyday": False, "category_ids": [2]})
        mock_api["delete"].assert_awaited_once_with("/organizer/places/1")
        assert mock_api["put"].await_count == 1  # no categories for a place taken off the list
        mock_api["patch"].assert_not_awaited()

    def test_archive_and_delete(self, client, mock_api):
        mock_api["get"].return_value = _place(active=False)
        mock_api["delete"].return_value = None

        assert client.patch("/places/1", json={"active": False}).status_code == 200
        mock_api["patch"].assert_awaited_once_with("/location/places/1", json={"active": False})
        assert client.delete("/places/1").status_code == 200
        mock_api["delete"].assert_awaited_once_with("/location/places/1")

    def test_place_in_use_message_is_relayed(self, client, mock_api):
        response = httpx.Response(409, json={"detail": "Cafe Example has visits: archive it instead"})
        mock_api["delete"].side_effect = httpx.HTTPStatusError("409", request=httpx.Request("DELETE", "/"), response=response)

        resp = client.delete("/places/1")

        assert resp.status_code == 409 and "archive it instead" in resp.json()["error"]


def _travel_time(id, origin, destination, mode="metro", minutes=20):
    return {"id": id, "origin": origin, "destination": destination, "mode": mode, "minutes": minutes,
            "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z"}


_HOME_REF = {"id": 1, "name": "Home", "kind": "home"}
_OFFICE_REF = {"id": 2, "name": "Office", "kind": "work"}


@pytest.mark.usefixtures("monday")
class TestTravelTimesCard:
    def test_lists_routes_with_links_to_the_other_end(self, client, mock_api):
        mock_api["get"].side_effect = _routes(
            place=_place(id=2, name="Office", kind="work"),
            places=[_place(id=1, name="Home", kind="home"), _place(id=2, name="Office", kind="work")],
            travel_times=[_travel_time(7, _HOME_REF, _OFFICE_REF, "metro", 50)],
        )

        text = client.get("/places/2").text

        assert 'id="travel-time-7"' in text
        assert '<a href="/places/1" class="hover:underline">Home</a>' in text and "50 min" in text
        destinations = re.search(r'name="destination_id".*?</select>', text, re.S).group(0)
        assert '<option value="1">Home</option>' in destinations and '<option value="2">' not in destinations
        assert "See all" not in text

    def test_caps_at_five_with_a_link_to_the_full_page(self, client, mock_api):
        routes = [_travel_time(i, _HOME_REF, _OFFICE_REF, f"mode{i}", i) for i in range(1, 8)]
        mock_api["get"].side_effect = _routes(place=_place(id=2, name="Office", kind="work"), travel_times=routes)

        text = client.get("/places/2").text

        assert len(re.findall(r'id="travel-time-\d+"', text)) == 5
        assert 'href="/places/2/travel-times"' in text and "See all 7" in text

    def test_full_page_lists_everything(self, client, mock_api):
        routes = [_travel_time(i, _HOME_REF, _OFFICE_REF, f"mode{i}", i) for i in range(1, 8)]
        mock_api["get"].side_effect = _routes(place=_place(id=2, name="Office", kind="work"), travel_times=routes)

        resp = client.get("/places/2/travel-times")

        assert resp.status_code == 200 and len(re.findall(r'id="travel-time-\d+"', resp.text)) == 7

    def test_full_page_missing_place_is_404(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=None)
        assert client.get("/places/9/travel-times").status_code == 404

    def test_no_other_place_means_no_form(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=_place(id=2), places=[_place(id=2)])

        text = client.get("/places/2").text

        assert 'id="travel-time-form"' not in text and "Add another everyday place" in text


class TestTravelTimeWrites:
    def test_set_and_delete_are_forwarded(self, client, mock_api):
        mock_api["put"].return_value = _travel_time(7, _HOME_REF, _OFFICE_REF)
        mock_api["delete"].return_value = None

        body = {"destination_id": 2, "mode": "metro", "minutes": 50}
        assert client.put("/places/1/travel-times", json=body).status_code == 200
        mock_api["put"].assert_awaited_once_with("/organizer/places/1/travel-times", json=body)
        assert client.delete("/places/travel-times/7").status_code == 200
        mock_api["delete"].assert_awaited_once_with("/organizer/travel-times/7")


def _calendar_event(id, start, title="Pickup", all_day=False):
    return {"id": id, "title": title, "start_datetime": start, "end_datetime": start, "all_day": all_day,
            "presence": "in_person"}


@pytest.mark.usefixtures("monday")
class TestPlaceEvents:
    def test_detail_lists_the_next_five_with_a_link_to_all(self, client, mock_api):
        events = [_calendar_event(i, f"2026-11-{23 + i}T17:00:00+00:00") for i in range(7)]
        mock_api["get"].side_effect = _routes(place=_place(id=3, name="School", kind="school"), events=list(reversed(events)))

        text = client.get("/places/3").text

        assert 'id="place-events"' in text
        assert text.count('data-event="') == 5
        assert "2026-11-23 17:00" in text and "2026-11-28 17:00" not in text
        assert 'href="/places/3/events"' in text and "See all 7" in text
        calls = [c for c in mock_api["get"].await_args_list if c.args[0] == "/organizer/calendar-events"]
        params = calls[0].kwargs["params"]
        assert params["place_id"] == 3
        assert params["start_from"] == "2026-11-23T00:00:00" and params["start_to"] == "2027-01-22T23:59:59"

    def test_full_page_lists_every_event(self, client, mock_api):
        events = [_calendar_event(i, f"2026-11-{23 + i}T17:00:00+00:00") for i in range(7)]
        mock_api["get"].side_effect = _routes(place=_place(id=3, name="School"), events=events)
        text = client.get("/places/3/events").text
        assert text.count('data-event="') == 7 and "Events at School in the next 60 days" in text

    def test_full_page_missing_place_is_404(self, client, mock_api):
        mock_api["get"].side_effect = _routes(place=None)
        assert client.get("/places/9/events").status_code == 404
