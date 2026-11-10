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


def _place():
    return {"id": 3, "kind": "hotel", "name": "Hotel Example", "city": "Beta", "country": None, "maps_url": None,
            "lat": None, "lng": None, "address": None, "notes": None, "maps_link": "https://maps.example/x"}


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
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [_place()]})
        html = client.get("/travel/1").text
        assert "Alpha → Beta" in html and "Check in: Hotel Example" in html
        assert "Arrives 5 h before check-in" in html
        assert "06:00" in html and "15:00" in html
        assert "Check flight" in html and "Cafes nearby" in html and "Luggage storage" in html
        assert "Ref ABC123" in html and "Grade 4/5" in html

    def test_groups_timeline_by_local_day(self, client, mock_api):
        detail = _detail()
        detail["timeline"][1]["local"] = "2026-12-18T09:00:00"
        _route(mock_api, {"/travel/trips/1": detail, "/travel/places": []})
        html = client.get("/travel/1").text
        assert "17 Dec 2026" in html and "18 Dec 2026" in html

    def test_no_warnings_block_when_clean(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(warnings=[]), "/travel/places": []})
        assert 'id="warnings"' not in client.get("/travel/1").text

    def test_empty_trip_explains_what_to_add(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(legs=[], stays=[], timeline=[], warnings=[]), "/travel/places": []})
        assert "Nothing booked yet" in client.get("/travel/1").text

    def test_unknown_trip_redirects_to_the_list(self, client, mock_api):
        _route(mock_api, {"/travel/trips/9": httpx.HTTPStatusError("x", request=httpx.Request("GET", "http://a"), response=httpx.Response(404))})
        resp = client.get("/travel/9", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/travel"

    def test_stay_form_offers_known_hotels(self, client, mock_api):
        _route(mock_api, {"/travel/trips/1": _detail(), "/travel/places": [_place()]})
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
    _route(mock_api, {"/travel/trips/1": detail, "/travel/places": []})
    html = client.get("/travel/1").text
    assert "Leave home for the airport" in html and "ti-door-exit" in html
