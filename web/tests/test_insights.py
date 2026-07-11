import httpx


def _memory(id=1, category="fact", content="Likes coffee", importance=0.5, active=True):
    return {
        "id": id, "category": category, "content": content,
        "importance": importance, "active": active, "created_at": "2026-07-01T00:00:00",
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
