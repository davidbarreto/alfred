import httpx


def _summary():
    return {
        "current_streak": 3,
        "longest_streak": 10,
        "total_solved": 42,
        "total_attempted": 50,
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
    return {"id": 7, "name": "Two Sum", "url": "https://codeforces.com/problemset/problem/1/A", "tags": [{"id": 1, "name": "dp"}]}


def _attempted_problem():
    return {
        "id": 7, "platform_id": 1, "external_id": "1A", "name": "Two Sum",
        "url": "https://codeforces.com/problemset/problem/1/A",
        "difficulty_raw": "1200", "difficulty": "easy",
        "tags_raw": ["dp"], "tags": [{"id": 1, "name": "dp"}],
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
    if path == "/cs/problems/tags":
        return ["dp", "graph"]
    if path == "/cs/stats/activity":
        return [{"date": "2026-07-30", "attempts": 2, "solved": 1}]
    return None


class TestDashboard:
    def test_renders_dashboard(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/")

        assert resp.status_code == 200
        assert "CS Coach" in resp.text
        assert "42" in resp.text  # total solved
        assert "Two Sum" in resp.text
        assert "Problems tried" in resp.text
        assert "Codeforces synced" in resp.text
        assert "LeetCode synced" in resp.text
        assert "View all" in resp.text
        assert 'href="/cs/submissions"' in resp.text
        assert 'href="/cs/problems"' in resp.text

    def test_does_not_render_platform_cards(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/")

        assert resp.status_code == 200
        assert "not configured" not in resp.text  # leetcode platform card handle placeholder

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


class TestActivityChartData:
    def test_maps_range_to_days(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/activity-chart-data?range=30")

        assert resp.status_code == 200
        assert resp.json() == {"solved": {"2026-07-30": 1}, "attempts": {"2026-07-30": 2}}
        activity_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/stats/activity"
        ]
        assert len(activity_calls) == 1
        assert activity_calls[0].kwargs["params"] == {"days": 30}

    def test_always_range_omits_days_param(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/activity-chart-data?range=always")

        assert resp.status_code == 200
        activity_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/stats/activity"
        ]
        assert activity_calls[0].kwargs["params"] == {}

    def test_defaults_to_90_days(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/activity-chart-data")

        assert resp.status_code == 200
        activity_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/stats/activity"
        ]
        assert activity_calls[0].kwargs["params"] == {"days": 90}


class TestProblemsPage:
    def test_renders_shell_without_blocking_on_data(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/problems")

        assert resp.status_code == 200
        assert "Problems tried" in resp.text
        assert "hx-trigger=\"load\"" in resp.text
        # the shell doesn't fetch attempted problems itself -- the section route does
        attempted_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/problems/attempted"
        ]
        assert len(attempted_calls) == 0

    def test_renders_tag_dropdown_options(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/problems")

        assert resp.status_code == 200
        assert ">Dp<" in resp.text
        assert ">Graph<" in resp.text

    def test_passes_filters_through_to_section_query(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/problems-section?platform_id=1&difficulty=easy&status=unsolved&q=Two")

        assert resp.status_code == 200
        attempted_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/problems/attempted"
        ]
        assert len(attempted_calls) == 1
        params = attempted_calls[0].kwargs["params"]
        assert params["platform_id"] == "1"
        assert params["difficulty"] == "easy"
        assert params["status"] == "unsolved"
        assert params["q"] == "Two"

    def test_returns_partial_for_htmx_pagination(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/problems-section?offset=0")

        assert resp.status_code == 200
        assert "Two Sum" in resp.text
        assert "CS Coach" not in resp.text  # partial, not full page

    def test_shows_tags_in_list(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/problems-section?offset=0")

        assert resp.status_code == 200
        assert "dp" in resp.text


class TestSubmissionsPage:
    def test_renders_shell_without_blocking_on_data(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/submissions")

        assert resp.status_code == 200
        assert "Submissions" in resp.text
        assert "hx-trigger=\"load\"" in resp.text
        submission_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/submissions"
        ]
        assert len(submission_calls) == 0

    def test_passes_filters_through_to_section_query(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get(
            "/cs/submissions-list-section?platform_id=1&verdict=accepted&tag=dp&q=Two"
        )

        assert resp.status_code == 200
        submission_calls = [
            call for call in mock_api["get"].await_args_list if call.args[0] == "/cs/submissions"
        ]
        assert len(submission_calls) == 1
        params = submission_calls[0].kwargs["params"]
        assert params["platform_id"] == "1"
        assert params["verdict"] == "accepted"
        assert params["tag"] == "dp"
        assert params["q"] == "Two"

    def test_returns_partial_with_tags_for_htmx_pagination(self, client, mock_api):
        mock_api["get"].side_effect = _get_side_effect

        resp = client.get("/cs/submissions-list-section?offset=0")

        assert resp.status_code == 200
        assert "Two Sum" in resp.text
        assert "dp" in resp.text
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
