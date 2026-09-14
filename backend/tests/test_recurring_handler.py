from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.recurring import handle_recurring


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.list = AsyncMock(return_value=[])
    return service


class TestHandleRecurringGet:
    async def test_returns_rule_when_found(self, mock_service):
        rule = MagicMock()
        rule.model_dump.return_value = {"id": 1, "merchant": "Netflix"}
        mock_service.get = AsyncMock(return_value=rule)

        result = await handle_recurring("get", {"id": "1"}, mock_service)

        mock_service.get.assert_awaited_once_with(1)
        assert result == {"id": 1, "merchant": "Netflix"}

    async def test_raises_404_when_not_found(self, mock_service):
        mock_service.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await handle_recurring("get", {"id": "999"}, mock_service)
        assert exc_info.value.status_code == 404


class TestHandleRecurringList:
    async def test_lists_with_default_filters(self, mock_service):
        await handle_recurring("list", {}, mock_service)

        called_filters = mock_service.list.call_args.args[0]
        assert called_filters.active is None
        assert called_filters.account_id is None

    async def test_casts_account_id_to_int(self, mock_service):
        await handle_recurring("list", {"account_id": "3"}, mock_service)

        called_filters = mock_service.list.call_args.args[0]
        assert called_filters.account_id == 3


class TestHandleRecurringUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_recurring("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
