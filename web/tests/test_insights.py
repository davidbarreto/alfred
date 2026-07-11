import httpx


def _memory(id=1, category="fact", content="Likes coffee", importance=0.5, active=True):
    return {
        "id": id, "category": category, "content": content,
        "importance": importance, "active": active, "created_at": "2026-07-01T00:00:00",
    }


def _wm(id=1, key="travel_context", value="Belgium next week", expires_at=None):
    return {
        "id": id, "key": key, "value": value,
        "importance": None, "expires_at": expires_at, "session_id": None,
        "created_at": "2026-07-01T00:00:00",
    }


def _llm_call(id=1, provider="google", model="gemini-2.5-flash", feature="chat",
              tokens_input=100, tokens_output=50, latency_ms=800):
    return {
        "id": id, "provider": provider, "model": model, "feature": feature,
        "tokens_input": tokens_input, "tokens_output": tokens_output, "latency_ms": latency_ms,
        "created_at": "2026-07-01T00:00:00",
    }


def _provider_call(id=1, provider="notion", operation="sync", entity_type="task", status="success"):
    return {
        "id": id, "provider": provider, "operation": operation, "entity_type": entity_type,
        "provider_entity_id": "abc", "status": status, "request_payload": None,
        "response_payload": None, "error": None, "command_execution_id": None,
        "created_at": "2026-07-01T00:00:00",
    }


class TestDeleteMemory:
    def test_deletes_memory_and_renders_updated_list(self, client, mock_api):
        mock_api["get"].return_value = [_memory(id=2, content="Remaining memory")]

        resp = client.delete("/insights/memories/1")

        assert resp.status_code == 200
        assert "Remaining memory" in resp.text
        mock_api["delete"].assert_awaited_once_with("/core/memories/1")
        mock_api["get"].assert_awaited_once_with("/core/memories", params={"limit": 21, "offset": 0})

    def test_preserves_category_filter_on_reload(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.delete("/insights/memories/1?category=fact")

        assert resp.status_code == 200
        mock_api["get"].assert_awaited_once_with(
            "/core/memories", params={"limit": 21, "offset": 0, "category": "fact"}
        )

    def test_returns_422_when_backend_delete_fails(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/core/memories/1")
        mock_api["delete"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.delete("/insights/memories/1")

        assert resp.status_code == 422


class TestWorkingMemorySection:
    def test_resolves_task_reminder_to_readable_label(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/working-memory":
                return [_wm(id=1, key="reminder:task:42:2026-07-11", value="reminded")]
            if path == "/organizer/tasks/42":
                return {"id": 42, "title": "Pay rent"}
            raise AssertionError(f"unexpected path {path}")

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/working-memory-section")

        assert resp.status_code == 200
        assert "Task: Pay rent" in resp.text
        assert "reminded 2026-07-11" in resp.text

    def test_resolves_shopping_reminder_without_entity_lookup(self, client, mock_api):
        mock_api["get"].return_value = [
            _wm(id=1, key="reminder:shopping:0:2026-07-11", value="reminded"),
        ]

        resp = client.get("/insights/working-memory-section")

        assert resp.status_code == 200
        assert "Shopping list: pending items reminder" in resp.text
        mock_api["get"].assert_awaited_once()

    def test_falls_back_to_placeholder_when_entity_deleted(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/working-memory":
                return [_wm(id=1, key="reminder:task:99:2026-07-11", value="reminded")]
            raise httpx.HTTPStatusError(
                "not found", request=httpx.Request("GET", "http://api/organizer/tasks/99"),
                response=httpx.Response(404, request=httpx.Request("GET", "http://api/organizer/tasks/99")),
            )

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/working-memory-section")

        assert resp.status_code == 200
        assert "Task: #99 (deleted)" in resp.text

    def test_non_reminder_entries_display_unchanged(self, client, mock_api):
        mock_api["get"].return_value = [
            _wm(id=1, key="travel_context", value="Belgium next week"),
        ]

        resp = client.get("/insights/working-memory-section")

        assert resp.status_code == 200
        assert "travel_context" in resp.text
        assert "Belgium next week" in resp.text


class TestInsightsPageLlmCharts:
    def test_computes_tokens_spent_per_feature(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/integration/llm-calls":
                return [
                    _llm_call(id=1, feature="chat", tokens_input=100, tokens_output=50),
                    _llm_call(id=2, feature="chat", tokens_input=200, tokens_output=100),
                    _llm_call(id=3, feature="briefing", tokens_input=10, tokens_output=5),
                ]
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "By feature" in resp.text
        assert "Tokens by feature" in resp.text
        assert "450" in resp.text  # chat: 100+50+200+100
        assert "View all" in resp.text

    def test_limits_recent_calls_preview_to_five(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/integration/llm-calls":
                return [_llm_call(id=i, latency_ms=100 + i) for i in range(1, 8)]
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "105 ms" in resp.text
        assert "106 ms" not in resp.text
        assert "107 ms" not in resp.text


class TestLlmCallsPage:
    def test_lists_calls_and_filter_dropdown_options(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("limit") == 500:
                return [
                    _llm_call(id=1, model="gemini-2.5-flash", feature="chat"),
                    _llm_call(id=2, model="gpt-4o-mini", feature="briefing"),
                ]
            return [_llm_call(id=1, model="gemini-2.5-flash", feature="chat")]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/llm-calls")

        assert resp.status_code == 200
        assert "gemini-2.5-flash" in resp.text
        assert "gpt-4o-mini" in resp.text  # only present via the model filter dropdown
        assert "briefing" in resp.text  # only present via the feature filter dropdown

    def test_applies_filters_as_backend_query_params(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            if params.get("limit") == 500:
                return []
            return [_llm_call(id=1, model="gemini-2.5-flash", feature="chat")]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/llm-calls?model=gemini-2.5-flash&feature=chat&q=hello")

        assert resp.status_code == 200
        main_call_params = next(p for p in seen_params if p.get("limit") != 500)
        assert main_call_params["model"] == "gemini-2.5-flash"
        assert main_call_params["feature"] == "chat"
        assert main_call_params["q"] == "hello"
        assert main_call_params["skip"] == 0

    def test_shows_next_link_when_more_than_a_page(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("limit") == 500:
                return []
            return [_llm_call(id=i) for i in range(21)]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/llm-calls")

        assert resp.status_code == 200
        assert "Next →" in resp.text
        assert "offset=20" in resp.text


class TestInsightsPageProviderCallsPreview:
    def test_limits_recent_provider_calls_preview_to_five(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/integration/provider-calls":
                return [_provider_call(id=i, operation=f"op-{i}") for i in range(1, 8)]
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "op-5" in resp.text
        assert "op-6" not in resp.text
        assert "op-7" not in resp.text
        assert '/insights/provider-calls" class="text-xs text-[#378ADD] hover:underline">View all' in resp.text


class TestProviderCallsPage:
    def test_lists_calls_and_filter_dropdown_options(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("limit") == 500:
                return [
                    _provider_call(id=1, provider="notion", operation="sync", entity_type="task"),
                    _provider_call(id=2, provider="google_calendar", operation="import", entity_type="event"),
                ]
            return [_provider_call(id=1, provider="notion", operation="sync", entity_type="task")]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/provider-calls")

        assert resp.status_code == 200
        assert "notion" in resp.text
        assert "google_calendar" in resp.text  # only present via the provider filter dropdown
        assert "import" in resp.text  # only present via the operation filter dropdown

    def test_applies_filters_as_backend_query_params(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            if params.get("limit") == 500:
                return []
            return [_provider_call(id=1)]

        mock_api["get"].side_effect = fake_get

        resp = client.get(
            "/insights/provider-calls?provider=notion&operation=sync&entity_type=task&status=error&q=oops"
        )

        assert resp.status_code == 200
        main_call_params = next(p for p in seen_params if p.get("limit") != 500)
        assert main_call_params["provider"] == "notion"
        assert main_call_params["operation"] == "sync"
        assert main_call_params["entity_type"] == "task"
        assert main_call_params["status"] == "error"
        assert main_call_params["q"] == "oops"
        assert main_call_params["skip"] == 0

    def test_shows_next_link_when_more_than_a_page(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("limit") == 500:
                return []
            return [_provider_call(id=i) for i in range(21)]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/provider-calls")

        assert resp.status_code == 200
        assert "Next →" in resp.text
        assert "offset=20" in resp.text
