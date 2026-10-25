from datetime import date

import httpx
import pytest


def _activity(id=1, title="Gym", **kw):
    base = {
        "id": id, "title": title, "min_minutes": None, "max_minutes": None, "context": None, "target_per_week": None,
        "tags": [], "archived_at": None, "last_done_at": None, "done_this_week": None,
    }
    base.update(kw)
    return base


def _stats(weeks=None, **kw):
    weeks = weeks if weeks is not None else [{"week_start": "2026-10-19", "count": 2, "minutes": 90}]
    return {"weeks": weeks, "by_activity": [], "by_tag": [], "total_count": sum(w["count"] for w in weeks),
            "total_minutes": sum(w["minutes"] for w in weeks), **kw}


def _routes(activities, stats):
    def fake_get(path, params=None):
        if path == "/organizer/activities":
            return activities
        if path == "/organizer/activities/stats":
            return stats
        raise AssertionError(path)

    return fake_get


@pytest.fixture
def wednesday(monkeypatch):
    monkeypatch.setattr("app.routes.activities.local_today", lambda: date(2026, 10, 21))


@pytest.mark.usefixtures("wednesday")
class TestActivitiesPage:
    def test_cards_show_range_tags_and_weekly_progress(self, client, mock_api):
        mock_api["get"].side_effect = _routes(
            [_activity(title="Gym", min_minutes=60, max_minutes=90, context="out", target_per_week=3, tags=["health"],
                       last_done_at="2026-10-18T18:00:00", done_this_week=1)],
            _stats(),
        )

        resp = client.get("/activities")

        assert resp.status_code == 200
        assert "Gym" in resp.text and "60–90 min" in resp.text and " · out" in resp.text
        assert "health" in resp.text
        assert "Last done 3 days ago" in resp.text
        assert "1/3 this week" in resp.text

    def test_never_done_and_done_today_labels(self, client, mock_api):
        mock_api["get"].side_effect = _routes(
            [_activity(1, "Never", ), _activity(2, "Today", last_done_at="2026-10-21T08:00:00")], _stats(),
        )
        text = client.get("/activities").text
        assert "Never done" in text and "Done today" in text

    def test_archived_are_requested_only_on_demand(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], _stats())
        client.get("/activities")
        assert mock_api["get"].await_args_list[0].kwargs["params"] == {"include_archived": "false"}
        client.get("/activities?archived=1")
        assert mock_api["get"].await_args_list[2].kwargs["params"] == {"include_archived": "true"}

    def test_archived_card_offers_restore_instead_of_log(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_activity(archived_at="2026-10-01T10:00:00")], _stats())
        text = client.get("/activities?archived=1").text
        assert "Restore" in text and "Log done" not in text

    def test_weekly_chart_scales_bars_to_the_busiest_week(self, client, mock_api):
        weeks = [
            {"week_start": "2026-10-05", "count": 4, "minutes": 0},
            {"week_start": "2026-10-12", "count": 0, "minutes": 0},
            {"week_start": "2026-10-19", "count": 1, "minutes": 30},
        ]
        mock_api["get"].side_effect = _routes([_activity()], _stats(weeks))
        text = client.get("/activities").text
        assert "height: 100%" in text and "height: 25%" in text and "activity-weekly-chart" in text

    def test_no_chart_without_logs(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_activity()], _stats([{"week_start": "2026-10-19", "count": 0, "minutes": 0}]))
        assert "activity-weekly-chart" not in client.get("/activities").text

    def test_page_survives_an_unreachable_backend(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        resp = client.get("/activities")
        assert resp.status_code == 200 and "unavailable" in resp.text

    def test_empty_state(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], _stats([]))
        assert "No activities yet" in client.get("/activities").text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/activities", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"].startswith("/login")

    def test_sidebar_links_to_the_new_pages(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], _stats([]))
        text = client.get("/activities").text
        for href in ('href="/activities"', 'href="/routines"', 'href="/plan"'):
            assert href in text


class TestActivityWrites:
    def test_create_forwards_the_body(self, client, mock_api):
        mock_api["post"].return_value = {"id": 5}
        resp = client.post("/activities", json={"title": "Read", "tags": ["quiet"]})
        assert resp.status_code == 200 and resp.json() == {"id": 5}
        mock_api["post"].assert_awaited_once_with("/organizer/activities", json={"title": "Read", "tags": ["quiet"]})

    def test_backend_validation_message_is_relayed(self, client, mock_api):
        request = httpx.Request("POST", "http://api/x")
        mock_api["post"].side_effect = httpx.HTTPStatusError(
            "bad", request=request, response=httpx.Response(422, json={"detail": "max_minutes must not be less"}, request=request)
        )
        resp = client.post("/activities", json={"title": "x"})
        assert resp.status_code == 422 and resp.json() == {"error": "max_minutes must not be less"}

    def test_log_posts_to_the_logs_endpoint(self, client, mock_api):
        mock_api["post"].return_value = {"id": 1}
        client.post("/activities/7/log", json={"minutes": 45})
        mock_api["post"].assert_awaited_once_with("/organizer/activities/7/logs", json={"minutes": 45})

    def test_log_of_archived_activity_relays_the_conflict(self, client, mock_api):
        request = httpx.Request("POST", "http://api/x")
        mock_api["post"].side_effect = httpx.HTTPStatusError(
            "conflict", request=request, response=httpx.Response(409, json={"detail": "Activity 7 is archived"}, request=request)
        )
        resp = client.post("/activities/7/log", json={})
        assert resp.status_code == 409 and "archived" in resp.json()["error"]

    def test_update(self, client, mock_api):
        mock_api["patch"].return_value = {"id": 7}
        client.patch("/activities/7", json={"target_per_week": 2})
        mock_api["patch"].assert_awaited_once_with("/organizer/activities/7", json={"target_per_week": 2})

    def test_archive_and_unarchive(self, client, mock_api):
        mock_api["post"].return_value = {"id": 7}
        assert client.post("/activities/7/archive").status_code == 200
        mock_api["post"].assert_awaited_with("/organizer/activities/7/archive")
        client.post("/activities/7/unarchive")
        mock_api["post"].assert_awaited_with("/organizer/activities/7/unarchive")

    def test_unknown_action_is_404(self, client, mock_api):
        assert client.post("/activities/7/delete").status_code == 404
        mock_api["post"].assert_not_called()

    def test_unreachable_backend_is_a_502(self, client, mock_api):
        mock_api["post"].side_effect = httpx.ConnectError("down")
        assert client.post("/activities", json={"title": "x"}).status_code == 502
