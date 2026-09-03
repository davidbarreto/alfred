from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.contacts.schemas import ContactRead
from app.features.organizer.interviews.processes.repository import InterviewProcessRepository
from app.features.organizer.interviews.stages.repository import InterviewStageRepository
from app.features.organizer.interviews.stages.schemas import (
    InterviewStageCreate,
    InterviewStageFilters,
    InterviewStageRead,
    InterviewStageUpdate,
)
from app.features.organizer.notes.schemas import NoteRead
from app.features.organizer.tasks.schemas import TaskRead

logger = logging.getLogger(__name__)


class InterviewStageService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = InterviewStageRepository(session)
        self._process_repo = InterviewProcessRepository(session)
        self._calendar_event_repo = CalendarEventRepository(session)

    async def get_stage(self, stage_id: int) -> InterviewStageRead | None:
        stage = await self._repo.get_stage(stage_id)
        return InterviewStageRead.model_validate(stage) if stage else None

    async def get_stages(self, filters: InterviewStageFilters) -> list[InterviewStageRead]:
        stages = await self._repo.get_stages(filters)
        return [InterviewStageRead.model_validate(s) for s in stages]

    async def _validate_refs(self, process_id: int | None, calendar_event_id: int | None) -> None:
        if process_id is not None:
            process = await self._process_repo.get_process(process_id)
            if process is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview process not found")
        if calendar_event_id is not None:
            event = await self._calendar_event_repo.get_event(calendar_event_id)
            if event is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found")

    async def create_stage(self, data: InterviewStageCreate) -> InterviewStageRead:
        await self._validate_refs(data.process_id, data.calendar_event_id)
        stage = await self._repo.create_stage(data)
        logger.info("Interview stage created: id=%d process_id=%d stage_type=%s", stage.id, stage.process_id, stage.stage_type)
        return InterviewStageRead.model_validate(stage)

    async def update_stage(self, stage_id: int, data: InterviewStageUpdate) -> InterviewStageRead | None:
        await self._validate_refs(None, data.calendar_event_id)
        stage = await self._repo.update_stage(stage_id, data)
        if stage is None:
            logger.debug("Interview stage update: id=%d not found", stage_id)
            return None
        logger.info("Interview stage updated: id=%d fields=%s", stage_id, list(data.model_dump(exclude_unset=True).keys()))
        return InterviewStageRead.model_validate(stage)

    async def delete_stage(self, stage_id: int) -> None:
        await self._repo.delete_stage(stage_id)
        logger.info("Interview stage deleted: id=%d", stage_id)

    async def add_stage_contact(self, stage_id: int, contact_id: int, role: str | None) -> None:
        await self._repo.add_stage_contact(stage_id, contact_id, role)
        logger.info("Interview stage contact linked: stage_id=%d contact_id=%d", stage_id, contact_id)

    async def remove_stage_contact(self, stage_id: int, contact_id: int) -> None:
        await self._repo.remove_stage_contact(stage_id, contact_id)
        logger.info("Interview stage contact unlinked: stage_id=%d contact_id=%d", stage_id, contact_id)

    async def list_stage_contacts(self, stage_id: int) -> list[ContactRead]:
        contacts = await self._repo.list_stage_contacts(stage_id)
        return [ContactRead.model_validate(c) for c in contacts]

    async def link_task(self, stage_id: int, task_id: int) -> None:
        await self._repo.link_task(stage_id, task_id)
        logger.info("Interview stage task linked: stage_id=%d task_id=%d", stage_id, task_id)

    async def unlink_task(self, stage_id: int, task_id: int) -> None:
        await self._repo.unlink_task(stage_id, task_id)
        logger.info("Interview stage task unlinked: stage_id=%d task_id=%d", stage_id, task_id)

    async def list_tasks(self, stage_id: int) -> list[TaskRead]:
        tasks = await self._repo.list_tasks(stage_id)
        return [TaskRead.model_validate(t) for t in tasks]

    async def link_note(self, stage_id: int, note_id: int) -> None:
        await self._repo.link_note(stage_id, note_id)
        logger.info("Interview stage note linked: stage_id=%d note_id=%d", stage_id, note_id)

    async def unlink_note(self, stage_id: int, note_id: int) -> None:
        await self._repo.unlink_note(stage_id, note_id)
        logger.info("Interview stage note unlinked: stage_id=%d note_id=%d", stage_id, note_id)

    async def list_notes(self, stage_id: int) -> list[NoteRead]:
        notes = await self._repo.list_notes(stage_id)
        return [NoteRead.model_validate(n) for n in notes]
