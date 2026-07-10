import pytest
from unittest.mock import AsyncMock

from app.assistant.commands.handlers.task import handle_task
from app.features.organizer.tasks.schemas import TaskFilters


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_tasks = AsyncMock(return_value=[])
    return service


class TestHandleTaskList:
    async def test_list_defaults_to_active_status(self, mock_service):
        await handle_task("list", {}, mock_service)

        called_filters = mock_service.get_tasks.call_args.args[0]
        assert isinstance(called_filters, TaskFilters)
        assert called_filters.status == "ACTIVE"

    async def test_list_respects_explicit_status(self, mock_service):
        await handle_task("list", {"status": "done"}, mock_service)

        called_filters = mock_service.get_tasks.call_args.args[0]
        assert called_filters.status == "DONE"
