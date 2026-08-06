from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.note import handle_note
from app.features.organizer.notes.schemas import NoteFilters


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_notes = AsyncMock(return_value=[])
    return service


class TestHandleNoteGet:
    async def test_returns_note_when_found(self, mock_service):
        note = MagicMock()
        note.model_dump.return_value = {"id": 29, "title": "Test note"}
        mock_service.get_note = AsyncMock(return_value=note)

        result = await handle_note("get", {"id": "29"}, mock_service)

        mock_service.get_note.assert_awaited_once_with(29)
        assert result == {"id": 29, "title": "Test note"}

    async def test_raises_404_when_not_found(self, mock_service):
        mock_service.get_note = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await handle_note("get", {"id": "999"}, mock_service)
        assert exc_info.value.status_code == 404


class TestHandleNoteList:
    async def test_lists_with_default_filters(self, mock_service):
        await handle_note("list", {}, mock_service)

        called_filters = mock_service.get_notes.call_args.args[0]
        assert isinstance(called_filters, NoteFilters)
        assert called_filters.limit == 100

    async def test_rejects_unexpected_positional_argument(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_note("list", {"task": "29"}, mock_service)
        assert exc_info.value.status_code == 400
        mock_service.get_notes.assert_not_awaited()
