import pytest
from unittest.mock import AsyncMock, MagicMock
from app.integrations.notion.provider import NotionProvider


def _make_client() -> AsyncMock:
    return AsyncMock()


def _make_page(page_id: str = "page-1", props: dict | None = None) -> dict:
    return {
        "id": page_id,
        "properties": props or {
            "title": {"type": "title", "title": [{"plain_text": "My Note"}]},
        },
    }


def _make_paragraph_block(text: str, block_id: str = "block-1") -> dict:
    return {
        "id": block_id,
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}, "plain_text": text}]
        },
    }


class TestTextToBlocks:
    def test_empty_string_returns_empty_list(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        assert provider._text_to_blocks("") == []

    def test_single_line(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        blocks = provider._text_to_blocks("Hello world")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "paragraph"
        assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Hello world"

    def test_preserves_newlines_as_separate_blocks(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        blocks = provider._text_to_blocks("Line one\nLine two\nLine three")
        assert len(blocks) == 3
        assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Line one"
        assert blocks[1]["paragraph"]["rich_text"][0]["text"]["content"] == "Line two"
        assert blocks[2]["paragraph"]["rich_text"][0]["text"]["content"] == "Line three"

    def test_empty_line_becomes_empty_paragraph(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        blocks = provider._text_to_blocks("Para one\n\nPara two")
        assert len(blocks) == 3
        assert blocks[1]["paragraph"]["rich_text"] == []

    def test_long_line_is_chunked(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        long_line = "x" * 4500
        blocks = provider._text_to_blocks(long_line)
        assert len(blocks) == 3
        assert len(blocks[0]["paragraph"]["rich_text"][0]["text"]["content"]) == 2000
        assert len(blocks[1]["paragraph"]["rich_text"][0]["text"]["content"]) == 2000
        assert len(blocks[2]["paragraph"]["rich_text"][0]["text"]["content"]) == 500


class TestBlocksToText:
    def test_empty_blocks_returns_empty_string(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        assert provider._blocks_to_text([]) == ""

    def test_single_block(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        block = _make_paragraph_block("Hello world")
        assert provider._blocks_to_text([block]) == "Hello world"

    def test_multiple_blocks_joined_by_newline(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        blocks = [_make_paragraph_block("Line one", "b1"), _make_paragraph_block("Line two", "b2")]
        assert provider._blocks_to_text(blocks) == "Line one\nLine two"

    def test_block_without_type_is_skipped(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        blocks = [{"id": "b1"}, _make_paragraph_block("Good block", "b2")]
        assert provider._blocks_to_text(blocks) == "Good block"

    def test_roundtrip_preserves_text(self):
        provider = NotionProvider(AsyncMock(), "db-id")
        original = "First line\nSecond line\nThird line"
        blocks = provider._text_to_blocks(original)
        # Simulate Notion adding plain_text to each rich_text item
        for block in blocks:
            for rt in block["paragraph"]["rich_text"]:
                rt["plain_text"] = rt["text"]["content"]
        result = provider._blocks_to_text(blocks)
        assert result == original


class TestCreateWithContentField:
    async def test_appends_blocks_after_page_creation(self):
        client = _make_client()
        page = _make_page("page-1")
        client.create_page.return_value = page
        client.append_block_children.return_value = {}

        provider = NotionProvider(client, "db-id", content_field="description")
        await provider.create({"title": "My Note", "description": "Some content here"})

        client.create_page.assert_called_once()
        client.append_block_children.assert_called_once()
        call_args = client.append_block_children.call_args
        assert call_args.args[0] == "page-1"
        blocks = call_args.args[1]
        assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Some content here"

    async def test_skips_append_when_description_empty(self):
        client = _make_client()
        client.create_page.return_value = _make_page()

        provider = NotionProvider(client, "db-id", content_field="description")
        await provider.create({"title": "My Note", "description": ""})

        client.append_block_children.assert_not_called()

    async def test_skips_append_when_no_content_field(self):
        client = _make_client()
        client.create_page.return_value = _make_page()

        provider = NotionProvider(client, "db-id")
        await provider.create({"title": "My Note", "description": "content"})

        client.append_block_children.assert_not_called()

    async def test_description_excluded_from_properties(self):
        client = _make_client()
        client.create_page.return_value = _make_page()

        provider = NotionProvider(client, "db-id", content_field="description")
        await provider.create({"title": "My Note", "description": "body text"})

        props = client.create_page.call_args.kwargs["properties"] if client.create_page.call_args.kwargs else client.create_page.call_args.args[1]
        assert "description" not in props


class TestGetWithContentField:
    async def test_fetches_blocks_and_injects_description(self):
        client = _make_client()
        client.get_page.return_value = _make_page("page-1")
        client.get_block_children.return_value = [_make_paragraph_block("Hello from body")]

        provider = NotionProvider(client, "db-id", content_field="description")
        result = await provider.get("page-1")

        client.get_block_children.assert_called_once_with("page-1")
        assert result["description"] == "Hello from body"

    async def test_multiline_description_joined_correctly(self):
        client = _make_client()
        client.get_page.return_value = _make_page("page-1")
        client.get_block_children.return_value = [
            _make_paragraph_block("Line one", "b1"),
            _make_paragraph_block("Line two", "b2"),
        ]

        provider = NotionProvider(client, "db-id", content_field="description")
        result = await provider.get("page-1")

        assert result["description"] == "Line one\nLine two"

    async def test_no_blocks_gives_empty_description(self):
        client = _make_client()
        client.get_page.return_value = _make_page("page-1")
        client.get_block_children.return_value = []

        provider = NotionProvider(client, "db-id", content_field="description")
        result = await provider.get("page-1")

        assert result["description"] == ""

    async def test_skips_block_fetch_without_content_field(self):
        client = _make_client()
        client.get_page.return_value = _make_page("page-1")

        provider = NotionProvider(client, "db-id")
        await provider.get("page-1")

        client.get_block_children.assert_not_called()


class TestUpdateWithContentField:
    async def test_clears_and_rewrites_blocks_when_description_present(self):
        client = _make_client()
        client.update_page.return_value = _make_page()
        client.get_block_children.return_value = [
            _make_paragraph_block("old content", "old-block-id"),
        ]

        provider = NotionProvider(client, "db-id", content_field="description")
        await provider.update("page-1", {"title": "Updated", "description": "new content"})

        client.delete_block.assert_called_once_with("old-block-id")
        client.append_block_children.assert_called_once()

    async def test_skips_block_operations_when_description_not_in_record(self):
        client = _make_client()
        client.update_page.return_value = _make_page()

        provider = NotionProvider(client, "db-id", content_field="description")
        await provider.update("page-1", {"title": "Updated"})

        client.get_block_children.assert_not_called()
        client.delete_block.assert_not_called()
        client.append_block_children.assert_not_called()

    async def test_clears_blocks_when_description_is_empty_string(self):
        client = _make_client()
        client.get_page.return_value = _make_page()
        client.get_block_children.return_value = [_make_paragraph_block("old", "old-id")]

        provider = NotionProvider(client, "db-id", content_field="description")
        await provider.update("page-1", {"description": ""})

        client.delete_block.assert_called_once_with("old-id")
        client.append_block_children.assert_not_called()

    async def test_uses_get_page_when_no_properties_to_update(self):
        client = _make_client()
        client.get_page.return_value = _make_page()
        client.get_block_children.return_value = []

        provider = NotionProvider(client, "db-id", content_field="description")
        await provider.update("page-1", {"description": "only content"})

        client.update_page.assert_not_called()
        client.get_page.assert_called_once_with("page-1")
