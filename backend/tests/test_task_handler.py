from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock

from app.assistant.commands.handlers.task import handle_task
from app.features.core.reminders.service import undated_escalation_snooze_key
from app.features.organizer.tasks.schemas import TaskFilters, TaskUpdate


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_tasks = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_working_memory_service():
    service = AsyncMock()
    service.list = AsyncMock(return_value=[])
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


class TestHandleTaskUpdate:
    async def test_update_urgency_field(self, mock_service):
        mock_service.update_task = AsyncMock(return_value=MagicMock())

        await handle_task("update", {"id": "1", "urgency": "normal"}, mock_service)

        mock_service.update_task.assert_awaited_once_with(1, TaskUpdate(urgency="NORMAL"))


class TestHandleTaskSnooze:
    async def test_snooze_creates_marker_with_default_days(self, mock_service, mock_working_memory_service):
        mock_service.get_task = AsyncMock(return_value=MagicMock(id=5))

        result = await handle_task(
            "snooze", {"id": "5"}, mock_service, working_memory_service=mock_working_memory_service
        )

        mock_working_memory_service.upsert.assert_awaited_once()
        created = mock_working_memory_service.upsert.call_args.args[0]
        assert created.key == undated_escalation_snooze_key(5)
        assert result == {"id": 5, "snoozed_until": created.expires_at.isoformat()}

    async def test_snooze_again_overwrites_existing_marker(self, mock_service, mock_working_memory_service):
        mock_service.get_task = AsyncMock(return_value=MagicMock(id=5))

        await handle_task(
            "snooze", {"id": "5"}, mock_service, working_memory_service=mock_working_memory_service
        )
        await handle_task(
            "snooze", {"id": "5"}, mock_service, working_memory_service=mock_working_memory_service
        )

        assert mock_working_memory_service.upsert.await_count == 2
        mock_working_memory_service.delete.assert_not_awaited()

    async def test_snooze_respects_explicit_days(self, mock_service, mock_working_memory_service):
        mock_service.get_task = AsyncMock(return_value=MagicMock(id=5))

        before = datetime.now(timezone.utc)
        await handle_task(
            "snooze", {"id": "5", "days": "3"}, mock_service, working_memory_service=mock_working_memory_service
        )

        created = mock_working_memory_service.upsert.call_args.args[0]
        assert 2 <= (created.expires_at - before).days <= 3

    async def test_snooze_task_not_found_raises_404(self, mock_service, mock_working_memory_service):
        mock_service.get_task = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await handle_task(
                "snooze", {"id": "5"}, mock_service, working_memory_service=mock_working_memory_service
            )
        assert exc_info.value.status_code == 404

    async def test_snooze_without_working_memory_service_raises_503(self, mock_service):
        mock_service.get_task = AsyncMock(return_value=MagicMock(id=5))

        with pytest.raises(HTTPException) as exc_info:
            await handle_task("snooze", {"id": "5"}, mock_service, working_memory_service=None)
        assert exc_info.value.status_code == 503
