import httpx


def _summary():
    return {
        "current_streak": 3,
        "longest_streak": 10,
        "total_solved": 42,
        "by_difficulty": [{"difficulty": "easy", "attempted": 10, "solved": 8}],
        "by_tag": [{"tag": "dp", "attempted": 5, "solved": 1, "solve_rate": 0.2, "submissions": 6, "avg_attempts_per_solve": 6.0}],
        "by_language": [{"language": "cpp", "solved": 20}],
        "by_day": [{"date": "2026-07-30", "attempts": 2, "solved": 1}],
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


def _attempted_problem():
    return {
        "id": 7, "platform_id": 1, "external_id": "1A", "name": "Two Sum",
        "url": "https://codeforces.com/problemset/problem/1/A",
        "difficulty_raw": "1200", "difficulty": "easy",
        "tags_raw": ["dp"], "tags": [{"id": 1, "name": "dp"}],
        "acceptance_rate": None, "solved_count": None, "likes": None, "dislikes": None,
        "metrics_updated_at": None,
        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
        "attempts": 2, "solved": True, "last_attempted_at": "2026-07-30T09:00:00",
    }


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
    if path == "/cs/problems/attempted":
        return [_attempted_problem()]
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
        assert "Problems tried" in resp.text
        assert "Codeforces synced" in resp.text
        assert "LeetCode synced" in resp.text
        assert "View all" in resp.text

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


class TestProblemsPage:
    def test_renders_full_page_and_triggers_metrics_refresh(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect
        mock_api["post"].return_value = {"updated": 0, "skipped": True}

        resp = client.get("/cs/problems")

        assert resp.status_code == 200
        assert "Two Sum" in resp.text
        refreshed_paths = {call.args[0] for call in mock_api["post"].await_args_list}
        assert "/cs/platforms/codeforces/refresh-metrics" in refreshed_paths
        assert "/cs/platforms/leetcode/refresh-metrics" in refreshed_paths

    def test_passes_filters_through_to_attempted_problems_query(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect
        mock_api["post"].return_value = {"updated": 0, "skipped": True}

        resp = client.get("/cs/problems?platform_id=1&difficulty=easy&q=Two")

        assert resp.status_code == 200
        attempted_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/problems/attempted"
        ]
        assert len(attempted_calls) == 1
        params = attempted_calls[0].kwargs["params"]
        assert params["platform_id"] == "1"
        assert params["difficulty"] == "easy"
        assert params["q"] == "Two"

    def test_returns_partial_for_htmx_pagination(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/problems-section?offset=0")

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
