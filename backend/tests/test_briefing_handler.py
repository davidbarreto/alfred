from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.briefing import handle_briefing


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.list = AsyncMock(return_value=[])
    return service


class TestHandleBriefingHistory:
    async def test_defaults(self, mock_service):
        await handle_briefing("history", {}, mock_service)

        mock_service.list.assert_awaited_once_with(briefing_type=None, limit=20, offset=0)

    async def test_passes_type_and_limit(self, mock_service):
        await handle_briefing("history", {"type": "morning", "limit": "5"}, mock_service)

        mock_service.list.assert_awaited_once_with(briefing_type="morning", limit=5, offset=0)


class TestHandleBriefingUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_briefing("generate", {}, mock_service)
        assert exc_info.value.status_code == 400
