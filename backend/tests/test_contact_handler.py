from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.contact import handle_contact


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_contacts = AsyncMock(return_value=[])
    return service


class TestHandleContactGet:
    async def test_returns_contact_when_found(self, mock_service):
        contact = MagicMock()
        contact.model_dump.return_value = {"id": 1, "name": "Test Person"}
        mock_service.get_contact = AsyncMock(return_value=contact)

        result = await handle_contact("get", {"id": "1"}, mock_service)

        mock_service.get_contact.assert_awaited_once_with(1)
        assert result == {"id": 1, "name": "Test Person"}

    async def test_raises_404_when_not_found(self, mock_service):
        mock_service.get_contact = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await handle_contact("get", {"id": "999"}, mock_service)
        assert exc_info.value.status_code == 404


class TestHandleContactList:
    async def test_lists_with_default_filters(self, mock_service):
        await handle_contact("list", {}, mock_service)

        called_filters = mock_service.get_contacts.call_args.args[0]
        assert called_filters.limit == 100
        assert called_filters.relationship is None


class TestHandleContactSearch:
    async def test_search_passes_name_filter(self, mock_service):
        await handle_contact("search", {"query": "David"}, mock_service)

        called_filters = mock_service.get_contacts.call_args.args[0]
        assert called_filters.name == "David"


class TestHandleContactUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_contact("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
