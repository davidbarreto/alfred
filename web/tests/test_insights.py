from datetime import datetime, timedelta, timezone

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


def _message(id=1, session_id=1, role="user", content="hello", meta=None):
    return {
        "id": id, "session_id": session_id, "role": role, "content": content,
        "meta": meta, "created_at": "2026-07-01T00:00:00",
    }


def _session(id=1, source="telegram", external_id="chat_1", summary=None, finished_at=None, last_interaction_at=None):
    if last_interaction_at is None:
        last_interaction_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return {
        "id": id, "source": source, "external_id": external_id, "summary": summary,
        "last_interaction_at": last_interaction_at, "created_at": "2026-07-01T00:00:00",
        "finished_at": finished_at,
    }


class TestDeleteMemory:
    def test_deletes_and_returns_empty_body(self, client, mock_api):
        resp = client.delete("/insights/memories/1")

        assert resp.status_code == 200
        assert resp.text == ""
        mock_api["delete"].assert_awaited_once_with("/core/memories/1")
        mock_api["get"].assert_not_awaited()

    def test_returns_422_when_backend_delete_fails(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/core/memories/1")
        mock_api["delete"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.delete("/insights/memories/1")

        assert resp.status_code == 422


class TestDeleteWorkingMemory:
    def test_deletes_and_returns_empty_body(self, client, mock_api):
        resp = client.delete("/insights/working-memory/1")

        assert resp.status_code == 200
        assert resp.text == ""
        mock_api["delete"].assert_awaited_once_with("/core/working-memory/1")
        mock_api["get"].assert_not_awaited()

    def test_returns_422_when_backend_delete_fails(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/core/working-memory/1")
        mock_api["delete"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.delete("/insights/working-memory/1")

        assert resp.status_code == 422


class TestInsightsPageWorkingMemoryPreview:
    def test_shows_up_to_five_entries_with_view_all_link(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/working-memory":
                return [_wm(id=i, key=f"travel_context_{i}") for i in range(1, 8)]
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "travel_context_5" in resp.text
        assert "travel_context_6" not in resp.text
        assert "travel_context_7" not in resp.text
        assert '/insights/working-memory" class="text-xs text-[#378ADD] hover:underline">View all' in resp.text
        assert "Prev" not in resp.text
        assert "Hide expired" not in resp.text

    def test_fetches_only_active_entries(self, client, mock_api):
        mock_api["get"].return_value = []

        client.get("/insights/")

        wm_call = next(
            c for c in mock_api["get"].call_args_list if c.args and c.args[0] == "/core/working-memory"
        )
        assert wm_call.kwargs["params"]["expired"] == "active"

    def test_resolves_task_reminder_to_readable_label(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/working-memory":
                return [_wm(id=1, key="reminder:task:42:2026-07-11", value="reminded")]
            if path == "/organizer/tasks/42":
                return {"id": 42, "title": "Pay rent"}
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "Task: Pay rent" in resp.text
        assert "reminded 2026-07-11" in resp.text

    def test_no_view_all_link_when_empty(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "No working memory entries." in resp.text


class TestInsightsPageMemoriesPreview:
    def test_shows_up_to_five_entries_with_view_all_link(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/memories":
                return [_memory(id=i, content=f"memory {i}") for i in range(1, 8)]
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "memory 5" in resp.text
        assert "memory 6" not in resp.text
        assert "memory 7" not in resp.text
        assert '/insights/memories" class="text-xs text-[#378ADD] hover:underline">View all' in resp.text

    def test_no_view_all_link_when_empty(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "No memories yet." in resp.text


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


class TestWorkingMemoryPage:
    def test_lists_items_and_filter_dropdown_options(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("expired") == "all":
                return [_wm(id=1, key="transient:a"), _wm(id=2, key="language:b")]
            return [_wm(id=1, key="transient:a", value="Fresh fact")]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/working-memory")

        assert resp.status_code == 200
        assert "Fresh fact" in resp.text
        assert 'value="transient"' in resp.text  # only present via the type filter dropdown
        assert 'value="language"' in resp.text

    def test_defaults_to_active_expiry_filter(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/working-memory")

        assert resp.status_code == 200
        main_call_params = next(p for p in seen_params if "limit" in p and p["limit"] != 200)
        assert main_call_params["expired"] == "active"

    def test_applies_filters_as_backend_query_params(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/working-memory?key_contains=travel&type=transient&expired=expired")

        assert resp.status_code == 200
        main_call_params = next(p for p in seen_params if p.get("expired") == "expired")
        assert main_call_params["key_contains"] == "travel"
        assert main_call_params["key_prefix"] == "transient"
        assert main_call_params["offset"] == 0

    def test_resolves_reminder_labels(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/working-memory":
                return [_wm(id=1, key="reminder:task:42:2026-07-11", value="reminded")]
            if path == "/organizer/tasks/42":
                return {"id": 42, "title": "Pay rent"}
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/working-memory")

        assert resp.status_code == 200
        assert "Task: Pay rent" in resp.text
        assert "reminded 2026-07-11" in resp.text

    def test_shows_next_link_when_more_than_a_page(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("expired") == "all":
                return []
            return [_wm(id=i, key=f"transient:{i}") for i in range(21)]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/working-memory")

        assert resp.status_code == 200
        assert "Next →" in resp.text
        assert "offset=20" in resp.text


class TestMemoriesPage:
    def test_lists_items_and_filter_dropdown_options(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("limit") == 200:
                return [_memory(id=1, category="fact"), _memory(id=2, category="goal")]
            return [_memory(id=1, category="fact", content="Likes coffee")]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/memories")

        assert resp.status_code == 200
        assert "Likes coffee" in resp.text
        assert 'value="fact"' in resp.text
        assert 'value="goal"' in resp.text  # only present via the category filter dropdown

    def test_defaults_to_importance_sort(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/memories")

        assert resp.status_code == 200
        main_call_params = next(p for p in seen_params if p.get("limit") != 200)
        assert main_call_params["sort"] == "importance"

    def test_applies_filters_as_backend_query_params(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/memories?category=fact&q=coffee&sort=created_at")

        assert resp.status_code == 200
        main_call_params = next(p for p in seen_params if p.get("sort") == "created_at")
        assert main_call_params["category"] == "fact"
        assert main_call_params["q"] == "coffee"
        assert main_call_params["offset"] == 0

    def test_shows_next_link_when_more_than_a_page(self, client, mock_api):
        async def fake_get(path, params=None):
            if params.get("limit") == 200:
                return []
            return [_memory(id=i) for i in range(21)]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/memories")

        assert resp.status_code == 200
        assert "Next →" in resp.text
        assert "offset=20" in resp.text


class TestInsightsPageMessagesPreview:
    def test_limits_recent_messages_preview_to_five(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/messages":
                return [_message(id=i, content=f"msg {i}") for i in range(1, 8)]
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "msg 5" in resp.text
        assert "msg 6" not in resp.text
        assert "msg 7" not in resp.text
        assert '/insights/messages" class="text-xs text-[#378ADD] hover:underline">View all' in resp.text


class TestInsightsPageSessionsPreview:
    def test_limits_recent_sessions_preview_to_five(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/core/sessions":
                return [_session(id=i, summary=f"session {i}") for i in range(1, 8)]
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/")

        assert resp.status_code == 200
        assert "session 5" in resp.text
        assert "session 6" not in resp.text
        assert "session 7" not in resp.text
        assert '/insights/sessions" class="text-xs text-[#378ADD] hover:underline">View all' in resp.text


class TestMessagesPage:
    def test_lists_messages(self, client, mock_api):
        mock_api["get"].return_value = [_message(id=1, content="hello there")]

        resp = client.get("/insights/messages")

        assert resp.status_code == 200
        assert "hello there" in resp.text

    def test_applies_filters_as_backend_query_params(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            return [_message(id=1)]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/messages?role=assistant&source=web&q=hello&session_id=42")

        assert resp.status_code == 200
        params = seen_params[0]
        assert params["role"] == "assistant"
        assert params["source"] == "web"
        assert params["q"] == "hello"
        assert params["session_id"] == "42"
        assert params["skip"] == 0

    def test_shows_next_link_when_more_than_a_page(self, client, mock_api):
        mock_api["get"].return_value = [_message(id=i) for i in range(21)]

        resp = client.get("/insights/messages")

        assert resp.status_code == 200
        assert "Next →" in resp.text
        assert "offset=20" in resp.text


class TestMessageDetail:
    def test_returns_detail_partial(self, client, mock_api):
        mock_api["get"].return_value = _message(id=1, content="the full content")

        resp = client.get("/insights/messages/1/detail")

        assert resp.status_code == 200
        assert "the full content" in resp.text

    def test_returns_422_when_backend_fails(self, client, mock_api):
        request = httpx.Request("GET", "http://api/core/messages/1")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/insights/messages/1/detail")

        assert resp.status_code == 422


class TestSessionsPage:
    def test_lists_sessions(self, client, mock_api):
        mock_api["get"].return_value = [_session(id=1, summary="Morning briefing")]

        resp = client.get("/insights/sessions")

        assert resp.status_code == 200
        assert "Morning briefing" in resp.text

    def test_applies_filters_as_backend_query_params(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            seen_params.append(params)
            return [_session(id=1)]

        mock_api["get"].side_effect = fake_get

        resp = client.get("/insights/sessions?source=telegram&active_only=true&q=briefing")

        assert resp.status_code == 200
        params = seen_params[0]
        assert params["source"] == "telegram"
        assert params["active_only"] is True
        assert params["q"] == "briefing"
        assert params["skip"] == 0

    def test_shows_next_link_when_more_than_a_page(self, client, mock_api):
        mock_api["get"].return_value = [_session(id=i) for i in range(21)]

        resp = client.get("/insights/sessions")

        assert resp.status_code == 200
        assert "Next →" in resp.text
        assert "offset=20" in resp.text


class TestSessionExpiryStatus:
    def test_recent_session_shows_active(self, client, mock_api):
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_api["get"].return_value = [_session(id=1, last_interaction_at=recent)]

        resp = client.get("/insights/sessions")

        assert resp.status_code == 200
        assert ">active<" in resp.text
        assert ">expired<" not in resp.text

    def test_session_past_expiry_hours_shows_expired(self, client, mock_api):
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        mock_api["get"].return_value = [_session(id=1, last_interaction_at=old)]

        resp = client.get("/insights/sessions")

        assert resp.status_code == 200
        assert ">expired<" in resp.text
        assert ">active<" not in resp.text

    def test_finished_session_shows_finished_even_if_recent(self, client, mock_api):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mock_api["get"].return_value = [_session(id=1, last_interaction_at=recent, finished_at=recent)]

        resp = client.get("/insights/sessions")

        assert resp.status_code == 200
        assert ">finished<" in resp.text
        assert ">active<" not in resp.text
        assert ">expired<" not in resp.text


class TestSessionDetail:
    def test_returns_detail_partial(self, client, mock_api):
        mock_api["get"].return_value = _session(id=1, summary="Detailed summary")

        resp = client.get("/insights/sessions/1/detail")

        assert resp.status_code == 200
        assert "Detailed summary" in resp.text

    def test_returns_422_when_backend_fails(self, client, mock_api):
        request = httpx.Request("GET", "http://api/core/sessions/1")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/insights/sessions/1/detail")

        assert resp.status_code == 422
