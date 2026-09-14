from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.account import handle_account


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.list = AsyncMock(return_value=[])
    return service


class TestHandleAccountGet:
    async def test_returns_account_when_found(self, mock_service):
        account = MagicMock()
        account.model_dump.return_value = {"id": 1, "name": "Checking"}
        mock_service.get = AsyncMock(return_value=account)

        result = await handle_account("get", {"id": "1"}, mock_service)

        mock_service.get.assert_awaited_once_with(1)
        assert result == {"id": 1, "name": "Checking"}

    async def test_raises_404_when_not_found(self, mock_service):
        mock_service.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await handle_account("get", {"id": "999"}, mock_service)
        assert exc_info.value.status_code == 404


class TestHandleAccountList:
    async def test_lists_with_default_filters(self, mock_service):
        await handle_account("list", {}, mock_service)

        called_filters = mock_service.list.call_args.args[0]
        assert called_filters.is_active is None
        assert called_filters.type is None
        assert called_filters.currency is None


class TestHandleAccountUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_account("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
