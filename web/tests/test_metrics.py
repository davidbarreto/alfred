import httpx
import pytest

from app.templates_config import _duration, _local_dt, _number


def _group(label, n=10, median=2000.0, p90=2500.0, low=False, key=None):
    return {
        "key": key or label, "label": label, "n": n, "median": median, "p90": p90, "mean": median,
        "min": None if median is None else median - 100, "max": None if median is None else median + 100,
        "low_confidence": low,
    }


def _stats(kind="duration", n=12, **overrides):
    overall = _group("All", n=n, key="all")
    stats = {
        "series": "commute-work", "kind": kind, "unit": None, "sample_threshold": 5, "excluded_over_cap": 0,
        "overall": overall,
        "by_tag": [_group("metro", 8, 2000), _group("bus", 12, 2400), _group("car", 2, 900, low=True)],
        "by_hour": [_group("08:00", 9), _group("17:00", 6)],
        "by_weekday": [_group("Mon", 5)],
        "by_weather": [_group("Dry", 10), _group("Rain", 5)],
        "trend": {"days": 30, "recent": _group("All", 6, 2000), "previous": _group("All", 7, 2200)},
        "best_tag": _group("metro", 8, 2000),
        "best_hour": _group("08:00", 9, 1900),
    }
    stats.update(overrides)
    return stats


def _series(name="commute-work", kind="duration", entry_count=12, unit=None):
    return {
        "id": 1, "name": name, "kind": kind, "unit": unit, "description": None, "is_archived": False,
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z", "entry_count": entry_count,
    }


def _entry(id=1, status="closed", duration_s=2040, tags=None, context=None, series_name="commute-work", **kw):
    return {
        "id": id, "series_id": 1, "series_name": series_name, "series_kind": "duration",
        "started_at": "2026-10-21T07:30:00Z", "ended_at": "2026-10-21T08:04:00Z" if status == "closed" else None,
        "duration_s": duration_s if status == "closed" else None, "value": kw.get("value"), "status": status,
        "is_stale": kw.get("is_stale", False), "source": "telegram", "context": context, "note": kw.get("note"),
        "tags": tags or [],
    }


def _status_error(status, detail):
    request = httpx.Request("POST", "http://api/x")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(status, request=request, json={"detail": detail}))


def _route(mock_api, routes):
    """get() answers by path prefix; longest match wins."""
    async def get(path, params=None):
        for prefix in sorted(routes, key=len, reverse=True):
            if path == prefix or path.startswith(prefix):
                value = routes[prefix]
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected GET {path}")

    mock_api["get"].side_effect = get


class TestFilters:
    @pytest.mark.parametrize("seconds,text", [(45, "45 s"), (2040, "34 min"), (3600, "1 h"), (3900, "1 h 05 min"), (None, "")])
    def test_duration(self, seconds, text):
        assert _duration(seconds) == text

    def test_local_dt_uses_the_configured_timezone(self):
        # Lisbon is UTC+1 in October (DST ended on the 25th), UTC+0 in winter
        assert _local_dt("2026-10-21T07:30:00Z") == "21 Oct 08:30"
        assert _local_dt("2026-12-01T07:30:00Z") == "01 Dec 07:30"
        assert _local_dt(None) == ""

    @pytest.mark.parametrize("value,text", [(7.5, "7.5"), (12.0, "12"), (0.25, "0.25"), (None, "")])
    def test_number(self, value, text):
        assert _number(value) == text


class TestMetricsPage:
    def test_lists_series_with_headline_numbers_and_running_timer(self, client, mock_api):
        _route(mock_api, {
            "/metrics/series/commute-work/stats": _stats(),
            "/metrics/series/sleep/stats": _stats("value", unit="h"),
            "/metrics/series": [_series(), _series("sleep", "value", 9, "h")],
            "/metrics/entries/open": [_entry(status="open")],
        })

        resp = client.get("/metrics")

        assert resp.status_code == 200
        assert "Metrics — Alfred Portal" in resp.text
        assert "commute-work" in resp.text and "sleep" in resp.text
        assert "33 min" in resp.text  # 2000 s median
        assert "running since" in resp.text
        assert 'href="/metrics/commute-work"' in resp.text

    def test_series_without_entries_skips_the_stats_call(self, client, mock_api):
        _route(mock_api, {"/metrics/series": [_series(entry_count=0)], "/metrics/entries/open": []})

        resp = client.get("/metrics")

        assert "No finished entries yet" in resp.text
        assert all("stats" not in c.args[0] for c in mock_api["get"].await_args_list)

    def test_flags_too_few_samples(self, client, mock_api):
        low = _stats(overall=_group("All", n=3, key="all", low=True))
        _route(mock_api, {
            "/metrics/series/commute-work/stats": low, "/metrics/series": [_series(entry_count=3)],
            "/metrics/entries/open": [],
        })
        assert "too few samples" in client.get("/metrics").text

    def test_empty_state_explains_how_to_start(self, client, mock_api):
        _route(mock_api, {"/metrics/series": [], "/metrics/entries/open": []})
        assert "/mstart" in client.get("/metrics").text

    def test_backend_down(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        resp = client.get("/metrics")
        assert resp.status_code == 200 and "unavailable" in resp.text

    def test_requires_login(self, anon_client):
        resp = anon_client.get("/metrics", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"].startswith("/login")

    def test_nav_link_present(self, client, mock_api):
        _route(mock_api, {"/metrics/series": [], "/metrics/entries/open": []})
        assert 'href="/metrics"' in client.get("/metrics").text


class TestSeriesPage:
    def _routes(self, **overrides):
        routes = {
            "/metrics/series/commute-work/stats": _stats(),
            "/metrics/series/commute-work": _series(),
            "/metrics/entries/open": [],
            "/metrics/tags": [{"id": 1, "name": "bus", "entry_count": 4}],
        }
        routes.update(overrides)
        return routes

    def test_edit_form_is_prefilled_and_hides_unit_for_timers(self, client, mock_api):
        _route(mock_api, self._routes(**{"/metrics/series/commute-work": _series(unit=None)}))
        html = client.get("/metrics/commute-work").text
        assert 'id="edit-series-form"' in html and 'value="commute-work"' in html
        assert 'name="unit"' not in html

    def test_edit_form_offers_the_unit_for_value_series(self, client, mock_api):
        _route(mock_api, self._routes(**{
            "/metrics/series/commute-work": _series(kind="value", unit="kg"),
            "/metrics/series/commute-work/stats": _stats("value"),
        }))
        html = client.get("/metrics/commute-work").text
        assert 'name="unit"' in html and 'value="kg"' in html

    def test_renders_stats_best_option_and_breakdowns(self, client, mock_api):
        _route(mock_api, self._routes())

        resp = client.get("/metrics/commute-work")

        assert resp.status_code == 200
        assert "Best option" in resp.text and "metro" in resp.text
        assert "Best hour to start" in resp.text and "08:00" in resp.text
        for heading in ("By tag", "By hour of day", "By weekday", "By weather"):
            assert heading in resp.text
        assert "33 min" in resp.text and "p90" in resp.text
        assert 'hx-get="/metrics/commute-work/history"' in resp.text
        assert "Start</button>" in resp.text

    def test_low_confidence_groups_are_dimmed_with_an_explanation(self, client, mock_api):
        _route(mock_api, self._routes())
        resp = client.get("/metrics/commute-work")
        assert "opacity-50" in resp.text and "Only 2 samples" in resp.text

    def test_running_timer_shows_stop_instead_of_start(self, client, mock_api):
        _route(mock_api, self._routes(**{"/metrics/entries/open": [_entry(status="open", tags=["bus"])]}))

        resp = client.get("/metrics/commute-work")

        assert "Running since" in resp.text and "stopTimer()" in resp.text and "startTimer()" not in resp.text

    def test_stale_running_timer_is_called_out(self, client, mock_api):
        _route(mock_api, self._routes(**{"/metrics/entries/open": [_entry(status="open", is_stale=True)]}))
        assert "forgot to stop" in client.get("/metrics/commute-work").text

    def test_running_timer_of_another_series_is_ignored(self, client, mock_api):
        _route(mock_api, self._routes(**{"/metrics/entries/open": [_entry(status="open", series_name="gym")]}))
        assert "Running since" not in client.get("/metrics/commute-work").text

    def test_filters_are_forwarded_to_the_stats_call(self, client, mock_api):
        _route(mock_api, self._routes())

        client.get("/metrics/commute-work?tag=bus&days=30")

        stats_call = next(c for c in mock_api["get"].await_args_list if c.args[0].endswith("/stats"))
        assert stats_call.kwargs["params"] == {"tag": "bus", "days": 30}

    def test_all_time_is_the_default_window(self, client, mock_api):
        _route(mock_api, self._routes())
        client.get("/metrics/commute-work")
        stats_call = next(c for c in mock_api["get"].await_args_list if c.args[0].endswith("/stats"))
        assert stats_call.kwargs["params"] == {}

    def test_value_series_has_a_value_input_and_no_p90(self, client, mock_api):
        _route(mock_api, {
            "/metrics/series/sleep/stats": _stats("value", unit="h"),
            "/metrics/series/sleep": _series("sleep", "value", unit="h"),
            "/metrics/entries/open": [], "/metrics/tags": [],
        })
        resp = client.get("/metrics/sleep")
        assert 'id="record-value"' in resp.text and "logEntry()" in resp.text
        assert ">p90<" not in resp.text

    def test_count_series_shows_events_not_percentiles(self, client, mock_api):
        counts = _stats("count", n=9)
        counts["by_tag"] = [_group("work", 9, None, None)]
        _route(mock_api, {
            "/metrics/series/coffee/stats": counts, "/metrics/series/coffee": _series("coffee", "count"),
            "/metrics/entries/open": [], "/metrics/tags": [],
        })
        resp = client.get("/metrics/coffee")
        assert "Events" in resp.text and "Median" not in resp.text

    def test_empty_series(self, client, mock_api):
        _route(mock_api, self._routes(**{"/metrics/series/commute-work/stats": _stats(n=0, overall=_group("All", n=0, key="all", median=None, p90=None, low=True))}))
        assert "No finished entries" in client.get("/metrics/commute-work").text

    def test_excluded_entries_are_explained(self, client, mock_api):
        _route(mock_api, self._routes(**{"/metrics/series/commute-work/stats": _stats(excluded_over_cap=2)}))
        assert "2 entries longer than 6 h" in client.get("/metrics/commute-work").text

    def test_unknown_series_redirects_to_the_list(self, client, mock_api):
        _route(mock_api, {"/metrics/series/ghost": httpx.HTTPError("404")})
        resp = client.get("/metrics/ghost", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/metrics"

    def test_series_name_cannot_alter_the_backend_path(self, client, mock_api):
        mock_api["get"].side_effect = httpx.HTTPError("404")
        client.get("/metrics/a%3Fb", follow_redirects=False)
        assert mock_api["get"].await_args_list[0].args[0] == "/metrics/series/a%3Fb"


class TestHistory:
    def test_renders_rows_with_rain_and_discard(self, client, mock_api):
        _route(mock_api, {
            "/metrics/entries": [_entry(1, tags=["bus"], context={"start": {"precipitation_mm": 1.2}}, note="late")],
            "/metrics/series/commute-work": _series(),
        })

        resp = client.get("/metrics/commute-work/history")

        assert resp.status_code == 200
        assert "34 min" in resp.text and "bus" in resp.text and "ti-cloud-rain" in resp.text
        assert "discardEntry(1)" in resp.text and "late" in resp.text
        assert mock_api["get"].await_args_list[0].kwargs["params"] == {"series": "commute-work", "limit": 16, "offset": 0}

    def test_discarded_entries_have_no_discard_button(self, client, mock_api):
        _route(mock_api, {"/metrics/entries": [_entry(1, status="discarded")], "/metrics/series/commute-work": _series()})
        resp = client.get("/metrics/commute-work/history")
        assert "discarded" in resp.text and "discardEntry(1)" not in resp.text

    def test_limit_plus_one_decides_has_next(self, client, mock_api):
        _route(mock_api, {"/metrics/entries": [_entry(i) for i in range(16)], "/metrics/series/commute-work": _series()})

        resp = client.get("/metrics/commute-work/history?offset=15&tag=bus")

        assert "entry-14" in resp.text and "entry-15" not in resp.text
        assert "offset=30" in resp.text and "offset=0" in resp.text and "tag=bus" in resp.text
        assert mock_api["get"].await_args_list[0].kwargs["params"]["offset"] == 15

    def test_empty(self, client, mock_api):
        _route(mock_api, {"/metrics/entries": [], "/metrics/series/commute-work": _series()})
        assert "No entries yet" in client.get("/metrics/commute-work/history").text

    def test_value_entries_show_the_unit(self, client, mock_api):
        entry = _entry(1, value=7.5)
        entry["series_kind"] = "value"
        _route(mock_api, {"/metrics/entries": [entry], "/metrics/series/sleep": _series("sleep", "value", unit="h")})
        assert "7.5 h" in client.get("/metrics/sleep/history").text


class TestWrites:
    def test_quick_action_forwards_body_and_result(self, client, mock_api):
        mock_api["post"].return_value = {"message": "Started commute-work [bus]"}

        resp = client.post("/metrics/quick/start", json={"series": "commute-work", "tags": ["bus"], "lat": 41.1, "lon": -8.6})

        assert resp.status_code == 200 and resp.json()["message"] == "Started commute-work [bus]"
        assert mock_api["post"].await_args.args[0] == "/metrics/quick/start"
        assert mock_api["post"].await_args.kwargs["json"]["lat"] == 41.1

    def test_unknown_quick_action(self, client, mock_api):
        assert client.post("/metrics/quick/nope", json={}).status_code == 404
        mock_api["post"].assert_not_awaited()

    def test_backend_conflict_message_reaches_the_page(self, client, mock_api):
        mock_api["post"].side_effect = _status_error(409, "Nothing running for commute-work")

        resp = client.post("/metrics/quick/stop", json={"series": "commute-work"})

        assert resp.status_code == 409 and resp.json() == {"error": "Nothing running for commute-work"}

    def test_validation_errors_fall_back_to_a_generic_message(self, client, mock_api):
        mock_api["post"].side_effect = _status_error(422, [{"msg": "bad"}])
        resp = client.post("/metrics/quick/start", json={})
        assert resp.status_code == 422 and resp.json()["error"] == "Could not reach the metrics service."

    def test_backend_down_is_502(self, client, mock_api):
        mock_api["post"].side_effect = httpx.ConnectError("down")
        assert client.post("/metrics/quick/log", json={"series": "x"}).status_code == 502

    def test_create_series(self, client, mock_api):
        mock_api["post"].return_value = {"name": "sleep"}
        resp = client.post("/metrics/series", json={"name": "Sleep", "kind": "value"})
        assert resp.status_code == 200 and mock_api["post"].await_args.args[0] == "/metrics/series"

    def test_update_series_patches_the_backend(self, client, mock_api):
        mock_api["patch"].return_value = {"name": "weight", "unit": "kg"}
        resp = client.patch("/metrics/series/weight", json={"unit": "kg"})
        assert resp.status_code == 200 and resp.json()["unit"] == "kg"
        assert mock_api["patch"].await_args.args[0] == "/metrics/series/weight"
        assert mock_api["patch"].await_args.kwargs["json"] == {"unit": "kg"}

    def test_update_series_relays_a_name_clash(self, client, mock_api):
        mock_api["patch"].side_effect = _status_error(409, "Series name already taken")
        resp = client.patch("/metrics/series/weight", json={"name": "sleep"})
        assert resp.status_code == 409 and resp.json()["error"] == "Series name already taken"

    def test_create_entry_and_discard(self, client, mock_api):
        mock_api["post"].return_value = {"id": 5}
        assert client.post("/metrics/entries", json={"series": "x"}).status_code == 200
        assert client.post("/metrics/entries/5/discard").status_code == 200
        assert mock_api["post"].await_args.args[0] == "/metrics/entries/5/discard"
