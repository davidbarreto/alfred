from datetime import date

import httpx
import pytest

from app.routes.locations import group_locations, maps_link, week_rows


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


def _routes(locations=None, location=None, categories=None):
    def fake_get(path, params=None):
        if path == "/organizer/locations":
            return locations if locations is not None else []
        if path.startswith("/organizer/locations/"):
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

    def test_new_form_lists_categories_and_kind_suggestions(self, client, mock_api):
        mock_api["get"].side_effect = _routes(locations=[], categories=[_GROCERIES, {"id": 2, "name": "pharmacy"}])

        text = client.get("/locations").text

        assert 'name="category_ids" value="2"' in text
        assert '<option value="pharmacy">' in text
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

    def test_holiday_banner(self, client, mock_api):
        mock_api["get"].side_effect = _routes(location=_location(
            opening_hours={"mon": [["08:00", "20:00"]]},
            today={"date": "2026-11-23", "hours": "08:00-20:00", "holiday": "Feriado", "note": "holiday, hours unknown",
                   "open_now": None},
        ))

        text = client.get("/locations/1").text

        assert "Today is a public holiday (Feriado): holiday, hours unknown." in text
        assert "Open now" not in text and "Closed now" not in text

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
        mock_api["post"].assert_awaited_once_with("/organizer/locations", json={"name": "Market", "opening_hours": "mon 8-20"})

    def test_backend_error_message_is_relayed(self, client, mock_api):
        response = httpx.Response(422, json={"detail": "Opening hours: 'funday' is not a day"})
        mock_api["post"].side_effect = httpx.HTTPStatusError("422", request=httpx.Request("POST", "/"), response=response)

        resp = client.post("/locations", json={"name": "Market", "opening_hours": "funday 9"})

        assert resp.status_code == 422
        assert resp.json() == {"error": "Opening hours: 'funday' is not a day"}

    def test_update_and_delete(self, client, mock_api):
        mock_api["patch"].return_value = _location(active=False)
        mock_api["delete"].return_value = None

        assert client.patch("/locations/1", json={"active": False}).status_code == 200
        mock_api["patch"].assert_awaited_once_with("/organizer/locations/1", json={"active": False})
        assert client.delete("/locations/1").status_code == 200
        mock_api["delete"].assert_awaited_once_with("/organizer/locations/1")
