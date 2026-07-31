import httpx


def _summary():
    return {
        "current_streak": 3,
        "longest_streak": 10,
        "total_solved": 42,
        "by_difficulty": [],
        "by_tag": [],
        "by_language": [],
        "weakest_tags": [{"tag": "dp", "attempted": 5, "solved": 1, "solve_rate": 0.2}],
    }


def _platforms():
    return [
        {"id": 1, "code": "codeforces", "handle": "tourist", "sync_enabled": True,
         "last_synced_at": "2026-07-30T10:00:00", "rating": 3500, "max_rating": 3600, "rank": "legendary"},
        {"id": 2, "code": "leetcode", "handle": None, "sync_enabled": False, "last_synced_at": None,
         "rating": None, "max_rating": None, "rank": None},
    ]


def _submission():
    return {
        "id": 1, "platform_id": 1, "problem_id": 7, "verdict": "accepted",
        "language": "cpp", "submitted_at": "2026-07-30T09:00:00",
    }


def _problem():
    return {"id": 7, "name": "Two Sum", "url": "https://codeforces.com/problemset/problem/1/A"}


def _get_side_effect(path, params=None):
    if path == "/cs/stats/summary":
        return _summary()
    if path == "/cs/recommendations/live":
        return None
    if path == "/cs/study-plans/active/weekly":
        return None
    if path == "/cs/platforms":
        return _platforms()
    if path == "/cs/submissions":
        return [_submission()]
    if path == "/cs/problems/7":
        return _problem()
    return None


class TestDashboard:
    def test_renders_dashboard(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/")

        assert resp.status_code == 200
        assert "CS Coach" in resp.text
        assert "42" in resp.text  # total solved
        assert "Codeforces" in resp.text
        assert "Two Sum" in resp.text

    def test_renders_empty_state_when_no_data(self, client, mock_api):
        mock_api["get"].side_effect = lambda path, params=None: None

        resp = client.get("/cs/")

        assert resp.status_code == 200
        assert "Not enough submission history yet." in resp.text
        assert "No active plan yet" in resp.text

    def test_renders_backend_unreachable_gracefully(self, client, mock_api):
        request = httpx.Request("GET", "http://api/cs/stats/summary")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/cs/")

        assert resp.status_code == 200


class TestSubmissionsSection:
    def test_returns_partial(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/submissions-section?offset=0")

        assert resp.status_code == 200
        assert "Two Sum" in resp.text
        assert "CS Coach" not in resp.text  # partial, not full page


class TestSyncTrigger:
    def test_rejects_unknown_platform(self, client, mock_api):
        resp = client.post("/cs/sync/hackerrank")
        assert resp.status_code == 404

    def test_triggers_codeforces_sync(self, client, mock_api):
        mock_api["post"].return_value = {"synced": 3}

        resp = client.post("/cs/sync/codeforces")

        assert resp.status_code == 200
        assert resp.json() == {"synced": 3}
        mock_api["post"].assert_awaited_once_with("/cs/platforms/codeforces/sync", timeout=60.0)

    def test_reports_backend_error(self, client, mock_api):
        request = httpx.Request("POST", "http://api/cs/platforms/leetcode/sync")
        response = httpx.Response(503, request=request, json={"detail": "LeetCode not configured."})
        mock_api["post"].side_effect = httpx.HTTPStatusError("error", request=request, response=response)

        resp = client.post("/cs/sync/leetcode")

        assert resp.status_code == 503
        assert resp.json() == {"error": "LeetCode not configured."}


class TestGeneratePlan:
    def test_rejects_unknown_cadence(self, client, mock_api):
        resp = client.post("/cs/plans/daily/generate")
        assert resp.status_code == 404

    def test_generates_weekly_plan(self, client, mock_api):
        mock_api["post"].return_value = {"id": 1, "cadence": "weekly", "items": []}

        resp = client.post("/cs/plans/weekly/generate")

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/cs/recommendations/plans/weekly", timeout=60.0)


class TestCompleteItem:
    def test_marks_item_complete(self, client, mock_api):
        mock_api["post"].return_value = None

        resp = client.post("/cs/plans/items/5/complete")

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/cs/study-plans/items/5/complete")
