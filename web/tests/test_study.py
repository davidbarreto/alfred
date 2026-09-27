import httpx


def _item(id, description, is_done=False, reason=None):
    return {
        "id": id, "description": description, "url": None, "is_done": is_done, "position": id,
        "source_type": "cs_tag" if reason else "manual", "source_id": None, "reason": reason,
    }


def _plan(id, title, status="active", priority="medium", items=None, tags=None):
    return {
        "id": id, "track_id": 1, "title": title, "goal": f"Goal for {title}", "priority": priority,
        "status": status, "activated_at": "2026-09-27T10:00:00", "completed_at": None,
        "tags": tags or [], "items": items or [],
        "created_at": "2026-09-27T10:00:00", "updated_at": "2026-09-27T10:00:00",
    }


def _overview(active=None, backlog=None, max_active_plans=3):
    return {"active": active or [], "backlog": backlog or [], "max_active_plans": max_active_plans}


def _status_error(method, path, status, detail):
    request = httpx.Request(method, f"http://api{path}")
    response = httpx.Response(status, request=request, json={"detail": detail})
    return httpx.HTTPStatusError("error", request=request, response=response)


class TestStudyPage:
    def test_renders_active_and_backlog(self, client, mock_api):
        mock_api["get"].return_value = _overview(
            active=[_plan(1, "Dynamic programming", tags=["algorithms"], items=[
                _item(1, "Review DP basics", is_done=True), _item(2, "Solve CF 1520E", reason="weakest tag"),
            ])],
            backlog=[_plan(2, "CAP theorem", status="backlog", priority="high")],
        )

        resp = client.get("/study")

        assert resp.status_code == 200
        mock_api["get"].assert_awaited_once_with("/study/plans/overview")
        assert "Study — Alfred Portal" in resp.text
        assert "Active plans" in resp.text and "(1/3)" in resp.text
        assert "Dynamic programming" in resp.text
        assert "algorithms" in resp.text
        assert "Why: weakest tag" in resp.text
        assert "1/2 done" in resp.text
        assert "CAP theorem" in resp.text
        assert 'hx-get="/study/history-section"' in resp.text

    def test_suggests_next_backlog_plan_when_a_slot_is_free(self, client, mock_api):
        mock_api["get"].return_value = _overview(backlog=[_plan(2, "CAP theorem", status="backlog")])

        resp = client.get("/study")

        assert "A slot is free" in resp.text

    def test_no_suggestion_and_start_disabled_at_the_cap(self, client, mock_api):
        mock_api["get"].return_value = _overview(
            active=[_plan(1, "Dynamic programming")],
            backlog=[_plan(2, "CAP theorem", status="backlog")],
            max_active_plans=1,
        )

        resp = client.get("/study")

        assert "A slot is free" not in resp.text
        assert "disabled title=" in resp.text  # Start button only disabled at the cap

    def test_nudges_to_close_plan_when_all_items_done(self, client, mock_api):
        mock_api["get"].return_value = _overview(
            active=[_plan(1, "Dynamic programming", items=[_item(1, "Review DP basics", is_done=True)])],
        )

        resp = client.get("/study")

        assert "Does this gap look closed?" in resp.text

    def test_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/study/plans/overview")
        mock_api["get"].side_effect = httpx.ConnectError("refused", request=request)

        resp = client.get("/study")

        assert resp.status_code == 200
        assert "Study plans are unavailable right now." in resp.text


class TestHistorySection:
    def test_renders_closed_plans_with_pagination(self, client, mock_api):
        plans = [_plan(i, f"Plan {i}", status="completed") for i in range(11)]
        mock_api["get"].return_value = plans

        resp = client.get("/study/history-section?offset=0")

        assert resp.status_code == 200
        mock_api["get"].assert_awaited_once_with(
            "/study/plans", params={"closed": "true", "limit": 11, "offset": 0}
        )
        assert "Plan 9" in resp.text
        assert "Plan 10" not in resp.text
        assert "<html" not in resp.text  # partial, not full page

    def test_empty_state(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/study/history-section")

        assert "No finished plans yet." in resp.text


class TestGeneratePlan:
    def test_proxies_to_backend(self, client, mock_api):
        mock_api["post"].return_value = _plan(1, "Dynamic programming")

        resp = client.post("/study/plans/generate")

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/study/plans/generate", timeout=60.0)

    def test_reports_backend_error(self, client, mock_api):
        mock_api["post"].side_effect = _status_error("POST", "/study/plans/generate", 502, "LLM returned invalid JSON")

        resp = client.post("/study/plans/generate")

        assert resp.status_code == 502
        assert resp.json() == {"error": "LLM returned invalid JSON"}


class TestPlanActions:
    def test_rejects_unknown_action(self, client, mock_api):
        assert client.post("/study/plans/1/pause").status_code == 404
        mock_api["post"].assert_not_awaited()

    def test_activate(self, client, mock_api):
        mock_api["post"].return_value = _plan(2, "CAP theorem")

        resp = client.post("/study/plans/2/activate")

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/study/plans/2/activate")

    def test_forwards_cap_conflict(self, client, mock_api):
        mock_api["post"].side_effect = _status_error(
            "POST", "/study/plans/2/activate", 409, "You already have 3 active plan(s). Finish or abandon one first."
        )

        resp = client.post("/study/plans/2/activate")

        assert resp.status_code == 409
        assert "3 active plan" in resp.json()["error"]

    def test_delete(self, client, mock_api):
        resp = client.delete("/study/plans/2")

        assert resp.status_code == 200
        mock_api["delete"].assert_awaited_once_with("/study/plans/2")

    def test_complete_item(self, client, mock_api):
        mock_api["post"].return_value = None

        resp = client.post("/study/items/5/complete")

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/study/plans/items/5/complete")
