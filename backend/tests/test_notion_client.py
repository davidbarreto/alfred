import pytest
from unittest.mock import AsyncMock, MagicMock
from app.integrations.notion.client import NotionClient


def _make_client() -> NotionClient:
    client = NotionClient(api_key="test-key", base_url="https://api.notion.com/v1")
    client._http = AsyncMock()
    return client


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    return resp


class TestAppendBlockChildren:
    async def test_posts_to_correct_url(self):
        client = _make_client()
        children = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}]
        client._http.patch = AsyncMock(return_value=_mock_response({"results": children}))

        result = await client.append_block_children("block-123", children)

        call_args = client._http.patch.call_args
        assert "blocks/block-123/children" in call_args.args[0]
        assert result == {"results": children}

    async def test_sends_children_in_body(self):
        client = _make_client()
        children = [{"type": "paragraph"}]
        client._http.patch = AsyncMock(return_value=_mock_response({}))

        await client.append_block_children("block-abc", children)

        call_kwargs = client._http.patch.call_args.kwargs
        assert call_kwargs["json"]["children"] == children


class TestGetBlockChildren:
    async def test_returns_results(self):
        client = _make_client()
        blocks = [{"id": "b1", "type": "paragraph"}, {"id": "b2", "type": "paragraph"}]
        client._http.get = AsyncMock(return_value=_mock_response({"results": blocks, "has_more": False}))

        result = await client.get_block_children("page-123")

        assert result == blocks

    async def test_paginates_when_has_more(self):
        client = _make_client()
        page1 = {"results": [{"id": "b1"}], "has_more": True, "next_cursor": "cursor-1"}
        page2 = {"results": [{"id": "b2"}], "has_more": False}
        client._http.get = AsyncMock(side_effect=[_mock_response(page1), _mock_response(page2)])

        result = await client.get_block_children("page-123")

        assert len(result) == 2
        assert result[0]["id"] == "b1"
        assert result[1]["id"] == "b2"

    async def test_empty_page_returns_empty_list(self):
        client = _make_client()
        client._http.get = AsyncMock(return_value=_mock_response({"results": [], "has_more": False}))

        result = await client.get_block_children("page-empty")

        assert result == []


class TestDeleteBlock:
    async def test_sends_delete_request(self):
        client = _make_client()
        delete_mock = AsyncMock(return_value=_mock_response({}))
        client._http.delete = delete_mock

        await client.delete_block("block-xyz")

        call_args = delete_mock.call_args
        assert "blocks/block-xyz" in call_args.args[0]
