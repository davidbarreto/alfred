from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.features.organizer.interviews.stages.schemas import InterviewStageCreate, InterviewStageUpdate
from app.features.organizer.interviews.stages.service import InterviewStageService


def _make_stage_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.process_id = kwargs.get("process_id", 1)
    orm.stage_type = kwargs.get("stage_type", "phone_screen")
    orm.scheduled_at = None
    orm.status = kwargs.get("status", "scheduled")
    orm.feedback = None
    orm.notes = None
    orm.sequence = kwargs.get("sequence", 0)
    orm.calendar_event_id = kwargs.get("calendar_event_id", None)
    orm.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    orm.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return orm


@pytest.fixture
def service():
    svc = InterviewStageService(session=AsyncMock())
    svc._repo = AsyncMock()
    svc._process_repo = AsyncMock()
    svc._calendar_event_repo = AsyncMock()
    return svc


class TestCreateStage:
    async def test_raises_404_when_process_missing(self, service):
        service._process_repo.get_process.return_value = None
        data = InterviewStageCreate(process_id=999, stage_type="phone_screen")
        with pytest.raises(HTTPException) as exc:
            await service.create_stage(data)
        assert exc.value.status_code == 404
        service._repo.create_stage.assert_not_called()

    async def test_raises_404_when_calendar_event_missing(self, service):
        service._process_repo.get_process.return_value = MagicMock()
        service._calendar_event_repo.get_event.return_value = None
        data = InterviewStageCreate(process_id=1, stage_type="phone_screen", calendar_event_id=999)
        with pytest.raises(HTTPException) as exc:
            await service.create_stage(data)
        assert exc.value.status_code == 404

    async def test_delegates_to_repo_when_valid(self, service):
        service._process_repo.get_process.return_value = MagicMock()
        service._repo.create_stage.return_value = _make_stage_orm()
        data = InterviewStageCreate(process_id=1, stage_type="phone_screen")
        result = await service.create_stage(data)
        service._repo.create_stage.assert_called_once_with(data)
        assert result.stage_type == "phone_screen"


class TestUpdateStage:
    async def test_returns_none_when_not_found(self, service):
        service._repo.update_stage.return_value = None
        result = await service.update_stage(999, InterviewStageUpdate(status="passed"))
        assert result is None

    async def test_returns_updated_stage(self, service):
        service._repo.update_stage.return_value = _make_stage_orm(status="passed")
        result = await service.update_stage(1, InterviewStageUpdate(status="passed"))
        assert result.status == "passed"


class TestDeleteStage:
    async def test_delegates_to_repo(self, service):
        await service.delete_stage(1)
        service._repo.delete_stage.assert_called_once_with(1)


class TestStageContactLinking:
    async def test_add_stage_contact_delegates_to_repo(self, service):
        await service.add_stage_contact(1, 2, "recruiter")
        service._repo.add_stage_contact.assert_called_once_with(1, 2, "recruiter")

    async def test_remove_stage_contact_delegates_to_repo(self, service):
        await service.remove_stage_contact(1, 2)
        service._repo.remove_stage_contact.assert_called_once_with(1, 2)

    async def test_list_stage_contacts_returns_read_schemas(self, service):
        contact = MagicMock()
        contact.id = 1
        contact.provider_id = "p1"
        contact.name = "Jane Doe"
        contact.email = None
        contact.phone = None
        contact.birthday = None
        contact.is_self = False
        contact.relationship = None
        service._repo.list_stage_contacts.return_value = [contact]
        result = await service.list_stage_contacts(1)
        assert result[0].name == "Jane Doe"


class TestStageTaskLinking:
    async def test_link_task_delegates_to_repo(self, service):
        await service.link_task(1, 5)
        service._repo.link_task.assert_called_once_with(1, 5)

    async def test_unlink_task_delegates_to_repo(self, service):
        await service.unlink_task(1, 5)
        service._repo.unlink_task.assert_called_once_with(1, 5)


class TestStageNoteLinking:
    async def test_link_note_delegates_to_repo(self, service):
        await service.link_note(1, 7)
        service._repo.link_note.assert_called_once_with(1, 7)

    async def test_unlink_note_delegates_to_repo(self, service):
        await service.unlink_note(1, 7)
        service._repo.unlink_note.assert_called_once_with(1, 7)
