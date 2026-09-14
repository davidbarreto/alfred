from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.interview import handle_interview


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_processes = AsyncMock(return_value=[])
    return service


class TestHandleInterviewGet:
    async def test_returns_process_when_found(self, mock_service):
        process = MagicMock()
        process.model_dump.return_value = {"id": 1, "role_title": "Backend Engineer"}
        mock_service.get_process = AsyncMock(return_value=process)

        result = await handle_interview("get", {"id": "1"}, mock_service)

        mock_service.get_process.assert_awaited_once_with(1)
        assert result == {"id": 1, "role_title": "Backend Engineer"}

    async def test_raises_404_when_not_found(self, mock_service):
        mock_service.get_process = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await handle_interview("get", {"id": "999"}, mock_service)
        assert exc_info.value.status_code == 404


class TestHandleInterviewList:
    async def test_lists_with_default_filters(self, mock_service):
        await handle_interview("list", {}, mock_service)

        called_filters = mock_service.get_processes.call_args.args[0]
        assert called_filters.limit == 50
        assert called_filters.company_id is None
        assert called_filters.status is None


class TestHandleInterviewUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_interview("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
