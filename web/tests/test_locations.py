import re
from datetime import date

import httpx
import pytest

from app.routes.locations import group_locations, maps_link, week_rows
from app.shared.location_kinds import KIND_ICONS, KINDS, location_icon


def _location(id=1, name="Market", kind="supermarket", **kw):
    base = {
        "id": id, "name": name, "kind": kind, "address": None, "maps_url": None, "opening_hours": None,
        "opening_hours_text": "", "notes": None, "active": True, "categories": [],
        "today": {"date": "2026-11-23", "hours": None, "holiday": None, "note": None, "open_now": None},
        "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z",
    }
    base.update(kw)
    return base


_GROCERIES = {"id": 1, "name": "groceries"}
_HOURS = {"mon": [["08:00", "13:00"], ["14:00", "20:00"]], "sun": [], "hol": []}


def _routes(locations=None, location=None, categories=None, travel_times=None, events=None):
    def fake_get(path, params=None):
        if path == "/organizer/calendar-events":
            return events if events is not None else []
        if path == "/organizer/places":
            return locations if locations is not None else []
        if path.endswith("/travel-times"):
            return travel_times if travel_times is not None else []
        if path.startswith("/organizer/places/"):
            if location is None:
                raise httpx.HTTPStatusError("404", request=httpx.Request("GET", path), response=httpx.Response(404))
            return location
        if path == "/organizer/shopping-categories":
            return categories if categories is not None else [_GROCERIES]
        raise AssertionError(path)

    return fake_get


@pytest.fixture
def monday(monkeypatch):
    monkeypatch.setattr("app.routes.locations.local_today", lambda: date(2026, 11, 23))


class TestHelpers:
    def test_week_rows_mark_today_and_unknown_days(self):
        rows = week_rows(_HOURS, "mon")

        assert rows[0] == {"label": "Monday", "hours": "08:00-13:00, 14:00-20:00", "today": True}
        assert rows[1]["hours"] == "unknown" and not rows[1]["today"]
        assert rows[6]["hours"] == "closed"
        assert rows[7] == {"label": "Public holidays", "hours": "closed", "today": False}

    def test_maps_link_prefers_saved_link_then_address_search(self):
        assert maps_link({"maps_url": "https://maps.example/x", "address": "Rua A 1"}) == "https://maps.example/x"
        assert maps_link({"maps_url": None, "address": "Rua A 1, Lisboa"}) == (
            "https://www.google.com/maps/search/?api=1&query=Rua+A+1%2C+Lisboa"
        )
        assert maps_link({"maps_url": None, "address": None}) is None

    def test_groups_places_then_shops_then_archived(self):
        home = _location(1, "Home", "home")
        shop = _location(2, "Market", categories=[_GROCERIES])
        old = _location(3, "Old gym", "gym", active=False)

        groups = group_locations([home, shop, old])

        assert [(title, [loc["name"] for loc in items]) for title, items in groups] == [
            ("Places", ["Home"]), ("Shops", ["Market"]), ("Archived", ["Old gym"]),
        ]

    def test_every_kind_has_its_own_icon(self):
        assert len(set(KIND_ICONS.values())) == len(KINDS)
        assert location_icon("work") == "ti-briefcase"

    def test_unknown_kind_falls_back_to_the_pin(self):
        assert location_icon("office") == "ti-map-pin"
        assert location_icon(None) == "ti-map-pin"

    def test_empty_groups_are_dropped(self):
        assert [title for title, _ in group_locations([_location(categories=[_GROCERIES])])] == ["Shops"]


class TestListPage:
    def test_cards_show_status_hours_and_categories(self, client, mock_api):
        mock_api["get"].side_effect = _routes(locations=[
            _location(1, "Home", "home", address="Rua A 1"),
            _location(2, "Market", opening_hours=_HOURS, categories=[_GROCERIES],
                      today={"date": "2026-11-23", "hours": "08:00-13:00, 14:00-20:00", "holiday": None, "note": None,
                             "open_now": True}),
        ])

        resp = client.get("/locations")

        assert resp.status_code == 200
        assert "Home" in resp.text and "Rua A 1" in resp.text
        assert "Open now" in resp.text
        assert "Today 08:00-13:00, 14:00-20:00" in resp.text
        assert 'id="group-places"' in resp.text and 'id="group-shops"' in resp.text
        assert 'href="/locations/2"' in resp.text

    def test_each_card_shows_its_kind_icon(self, client, mock_api):
        mock_api["get"].side_effect = _routes(locations=[_location(1, "Home", "home"), _location(2, "Pharmacy", "pharmacy")])

        text = client.get("/locations").text

        assert '<i class="ti ti-home text-sm" title="home"></i> Home' in text
        assert '<i class="ti ti-pill text-sm" title="pharmacy"></i> Pharmacy' in text

    def test_holiday_note_and_closed(self, client, mock_api):
        mock_api["get"].side_effect = _routes(locations=[_location(
            opening_hours=_HOURS,
            today={"date": "2026-11-23", "hours": "closed", "holiday": "Feriado", "note": "holiday hours", "open_now": False},
        )])

        text = client.get("/locations").text

        assert "Closed today · holiday hours" in text and ">Closed<" in text

    def test_empty_and_unavailable(self, client, mock_api):
        mock_api["get"].side_effect = _routes(locations=[])
        assert "No locations yet" in client.get("/locations").text

        def failing(path, params=None):
            raise httpx.ConnectError("down")
        mock_api["get"].side_effect = failing
        assert "unavailable right now" in client.get("/locations").text

    def test_new_form_lists_categories_and_offers_only_the_fixed_kinds(self, client, mock_api):
        mock_api["get"].side_effect = _routes(locations=[], categories=[_GROCERIES, {"id": 2, "name": "pharmacy"}])

        text = client.get("/locations").text

        assert 'name="category_ids" value="2"' in text
        assert '<select name="kind"' in text and "<datalist" not in text
        assert '<option value="pharmacy">pharmacy</option>' in text
        assert '<option value="other" selected>other</option>' in text
        assert 'data-url="/locations" data-method="POST"' in text


@pytest.mark.usefixtures("monday")
class TestDetailPage:
    def test_shows_week_with_today_address_and_categories(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(
            address="Rua A 1", opening_hours=_HOURS, opening_hours_text="mon 08:00-13:00, 14:00-20:00; sun closed",
            categories=[_GROCERIES],
            today={"date": "2026-11-23", "hours": "08:00-13:00, 14:00-20:00", "holiday": None, "note": None, "open_now": True},
        ))

        resp = client.get("/locations/1")

        assert resp.status_code == 200
        assert "data-today" in resp.text and "Monday" in resp.text
        assert "Open now" in resp.text
        assert "maps/search/?api=1&amp;query=Rua+A+1" in resp.text
        assert 'name="category_ids" value="1" class="checkbox checkbox-xs"\n               checked' in resp.text
        assert "mon 08:00-13:00, 14:00-20:00\nsun closed</textarea>" in resp.text
        assert 'data-url="/locations/1" data-method="PATCH"' in resp.text

    def test_edit_form_selects_the_location_kind(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(kind="work", name="Office"))

        text = client.get("/locations/1").text

        assert '<option value="work" selected>work</option>' in text
        assert '<option value="other">other</option>' in text

    def test_edit_form_shows_the_coordinates(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(latitude=41.1579, longitude=-8.6291))
        assert 'name="coordinates" value="41.1579, -8.6291"' in client.get("/locations/1").text

    def test_edit_form_without_coordinates_is_empty(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location())
        assert 'name="coordinates" value=""' in client.get("/locations/1").text

    def test_title_shows_the_kind_icon(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(kind="cafe", name="Corner cafe"))
        assert '<i class="ti ti-coffee"></i> Corner cafe' in client.get("/locations/1").text

    def test_holiday_banner(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(
            opening_hours={"mon": [["08:00", "20:00"]]},
            today={"date": "2026-11-23", "hours": "08:00-20:00", "holiday": "Feriado", "note": "holiday, hours unknown",
                   "open_now": None},
        ))

        text = client.get("/locations/1").text

        assert "Today is a public holiday (Feriado): holiday, hours unknown." in text
        assert "Open now" not in text and "Closed now" not in text

    def test_home_form_remembers_the_address_to_detect_a_move(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(kind="home", name="Home", address="Rua A 1"))

        text = client.get("/locations/1").text

        assert 'data-home-address="Rua A 1"' in text
        assert 'id="home-moved"' not in text

    def test_moved_banner_only_for_home(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(kind="home", name="Home"))
        assert 'id="home-moved"' in client.get("/locations/1?moved=1").text

        mock_api["get"].side_effect = _routes(location=_location())
        text = client.get("/locations/1?moved=1").text
        assert 'id="home-moved"' not in text and "data-home-address" not in text

    def test_unknown_hours(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location())

        assert "Hours unknown" in client.get("/locations/1").text

    def test_missing_location_is_404(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=None)

        resp = client.get("/locations/9")

        assert resp.status_code == 404 and "does not exist" in resp.text


class TestWrites:
    def test_create_forwards_to_backend(self, client, mock_api):
        mock_api["post"].return_value = _location(id=5)

        resp = client.post("/locations", json={"name": "Market", "opening_hours": "mon 8-20"})

        assert resp.status_code == 200 and resp.json()["id"] == 5
        mock_api["post"].assert_awaited_once_with("/organizer/places", json={"name": "Market", "opening_hours": "mon 8-20"})

    def test_backend_error_message_is_relayed(self, client, mock_api):
        response = httpx.Response(422, json={"detail": "Opening hours: 'funday' is not a day"})
        mock_api["post"].side_effect = httpx.HTTPStatusError("422", request=httpx.Request("POST", "/"), response=response)

        resp = client.post("/locations", json={"name": "Market", "opening_hours": "funday 9"})

        assert resp.status_code == 422
        assert resp.json() == {"error": "Opening hours: 'funday' is not a day"}

    def test_update_and_delete(self, client, mock_api):
        mock_api["get"].return_value = _location(active=False)
        mock_api["delete"].return_value = None

        assert client.patch("/locations/1", json={"active": False}).status_code == 200
        mock_api["patch"].assert_awaited_once_with("/location/places/1", json={"active": False})
        mock_api["put"].assert_not_awaited()
        mock_api["get"].assert_awaited_once_with("/organizer/places/1")
        assert client.delete("/locations/1").status_code == 200
        mock_api["delete"].assert_awaited_once_with("/location/places/1")

    def test_update_sends_what_it_sells_to_the_everyday_api(self, client, mock_api):
        mock_api["get"].return_value = _location()

        response = client.patch("/locations/1", json={"name": "Market", "category_ids": [2]})

        assert response.status_code == 200
        mock_api["patch"].assert_awaited_once_with("/location/places/1", json={"name": "Market"})
        mock_api["put"].assert_awaited_once_with("/organizer/places/1/categories", json={"category_ids": [2]})

    def test_categories_alone_skip_the_place_patch(self, client, mock_api):
        mock_api["get"].return_value = _location()

        client.patch("/locations/1", json={"category_ids": []})

        mock_api["patch"].assert_not_awaited()


def _travel_time(id, origin, destination, mode="metro", minutes=20):
    return {"id": id, "origin": origin, "destination": destination, "mode": mode, "minutes": minutes,
            "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z"}


_HOME_REF = {"id": 1, "name": "Home", "kind": "home"}
_OFFICE_REF = {"id": 2, "name": "Office", "kind": "work"}


@pytest.mark.usefixtures("monday")
class TestTravelTimesCard:
    def test_lists_routes_with_links_to_the_other_end(self, client, mock_api):
        mock_api["get"].side_effect = _routes(
            location=_location(id=2, name="Office", kind="work"),
            locations=[_location(id=1, name="Home", kind="home"), _location(id=2, name="Office", kind="work")],
            travel_times=[_travel_time(7, _HOME_REF, _OFFICE_REF, "metro", 50)],
        )

        text = client.get("/locations/2").text

        assert 'id="travel-time-7"' in text
        assert '<a href="/locations/1" class="hover:underline">Home</a>' in text and "50 min" in text
        # The form offers every other active location, not this one.
        assert '<option value="1">Home</option>' in text and '<option value="2">' not in text
        assert "See all" not in text

    def test_caps_at_five_with_a_link_to_the_full_page(self, client, mock_api):
        routes = [_travel_time(i, _HOME_REF, _OFFICE_REF, f"mode{i}", i) for i in range(1, 8)]
        mock_api["get"].side_effect = _routes(location=_location(id=2, name="Office", kind="work"), travel_times=routes)

        text = client.get("/locations/2").text

        assert len(re.findall(r'id="travel-time-\d+"', text)) == 5
        assert 'href="/locations/2/travel-times"' in text and "See all 7" in text

    def test_full_page_lists_everything(self, client, mock_api):
        routes = [_travel_time(i, _HOME_REF, _OFFICE_REF, f"mode{i}", i) for i in range(1, 8)]
        mock_api["get"].side_effect = _routes(location=_location(id=2, name="Office", kind="work"), travel_times=routes)

        resp = client.get("/locations/2/travel-times")

        assert resp.status_code == 200 and len(re.findall(r'id="travel-time-\d+"', resp.text)) == 7

    def test_full_page_missing_location_is_404(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=None)

        assert client.get("/locations/9/travel-times").status_code == 404

    def test_no_other_location_means_no_form(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(id=2), locations=[_location(id=2)])

        text = client.get("/locations/2").text

        assert 'id="travel-time-form"' not in text and "Add another location" in text


class TestTravelTimeWrites:
    def test_set_and_delete_are_forwarded(self, client, mock_api):
        mock_api["put"].return_value = _travel_time(7, _HOME_REF, _OFFICE_REF)
        mock_api["delete"].return_value = None

        body = {"destination_id": 2, "mode": "metro", "minutes": 50}
        assert client.put("/locations/1/travel-times", json=body).status_code == 200
        mock_api["put"].assert_awaited_once_with("/organizer/places/1/travel-times", json=body)
        assert client.delete("/locations/travel-times/7").status_code == 200
        mock_api["delete"].assert_awaited_once_with("/organizer/travel-times/7")


def _calendar_event(id, start, title="Pickup", all_day=False):
    return {"id": id, "title": title, "start_datetime": start, "end_datetime": start, "all_day": all_day,
            "presence": "in_person"}


@pytest.mark.usefixtures("monday")
class TestLocationEvents:
    def test_detail_lists_the_next_five_with_a_link_to_all(self, client, mock_api):
        events = [_calendar_event(i, f"2026-11-{23 + i}T17:00:00+00:00") for i in range(7)]
        mock_api["get"].side_effect = _routes(location=_location(id=3, name="School"), events=list(reversed(events)))

        text = client.get("/locations/3").text

        assert 'id="location-events"' in text
        assert text.count('data-event="') == 5
        assert "2026-11-23 17:00" in text and "2026-11-28 17:00" not in text  # sorted, capped at 5
        assert 'href="/locations/3/events"' in text and "See all 7" in text
        calls = [c for c in mock_api["get"].await_args_list if c.args[0] == "/organizer/calendar-events"]
        params = calls[0].kwargs["params"]
        assert params["place_id"] == 3
        assert params["start_from"] == "2026-11-23T00:00:00" and params["start_to"] == "2027-01-22T23:59:59"

    def test_no_link_when_everything_fits(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(), events=[_calendar_event(1, "2026-11-24T09:00:00+00:00")])
        text = client.get("/locations/1").text
        assert "See all" not in text and 'data-event="1"' in text

    def test_full_page_lists_every_event(self, client, mock_api):
        events = [_calendar_event(i, f"2026-11-{23 + i}T17:00:00+00:00") for i in range(7)]
        mock_api["get"].side_effect = _routes(location=_location(id=3, name="School"), events=events)
        text = client.get("/locations/3/events").text
        assert text.count('data-event="') == 7 and "Events at School in the next 60 days" in text

    def test_full_page_missing_location_is_404(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=None)
        assert client.get("/locations/9/events").status_code == 404
