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
