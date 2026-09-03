from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.contacts.tables import Contact
from app.features.organizer.interviews.stages.schemas import InterviewStageCreate, InterviewStageFilters, InterviewStageUpdate
from app.features.organizer.interviews.stages.tables import (
    InterviewStage,
    interview_stage_contacts,
    interview_stage_notes,
    interview_stage_tasks,
)
from app.features.organizer.notes.tables import Note
from app.features.organizer.tasks.tables import Task


class InterviewStageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_stage(self, stage_id: int) -> InterviewStage | None:
        result = await self._session.execute(select(InterviewStage).where(InterviewStage.id == stage_id))
        return result.scalars().first()

    async def get_stages(self, filters: InterviewStageFilters) -> list[InterviewStage]:
        stmt = select(InterviewStage)
        if filters.process_id is not None:
            stmt = stmt.where(InterviewStage.process_id == filters.process_id)
        if filters.status is not None:
            stmt = stmt.where(InterviewStage.status == filters.status)
        stmt = stmt.order_by(InterviewStage.sequence).offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_stage(self, data: InterviewStageCreate) -> InterviewStage:
        stage = InterviewStage(**data.model_dump())
        self._session.add(stage)
        await self._session.commit()
        await self._session.refresh(stage)
        return stage

    async def update_stage(self, stage_id: int, data: InterviewStageUpdate) -> InterviewStage | None:
        stage = await self.get_stage(stage_id)
        if stage is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(stage, field, value)
        await self._session.commit()
        await self._session.refresh(stage)
        return stage

    async def delete_stage(self, stage_id: int) -> None:
        stage = await self.get_stage(stage_id)
        if stage is not None:
            await self._session.delete(stage)
            await self._session.commit()

    # -- stage <-> contact association --

    async def add_stage_contact(self, stage_id: int, contact_id: int, role: str | None) -> None:
        await self._session.execute(
            interview_stage_contacts.insert().values(stage_id=stage_id, contact_id=contact_id, role=role)
        )
        await self._session.commit()

    async def remove_stage_contact(self, stage_id: int, contact_id: int) -> None:
        await self._session.execute(
            delete(interview_stage_contacts).where(
                interview_stage_contacts.c.stage_id == stage_id,
                interview_stage_contacts.c.contact_id == contact_id,
            )
        )
        await self._session.commit()

    async def list_stage_contacts(self, stage_id: int) -> list[Contact]:
        result = await self._session.execute(
            select(Contact)
            .join(interview_stage_contacts, interview_stage_contacts.c.contact_id == Contact.id)
            .where(interview_stage_contacts.c.stage_id == stage_id)
        )
        return list(result.scalars().all())

    # -- stage <-> task association --

    async def link_task(self, stage_id: int, task_id: int) -> None:
        await self._session.execute(interview_stage_tasks.insert().values(stage_id=stage_id, task_id=task_id))
        await self._session.commit()

    async def unlink_task(self, stage_id: int, task_id: int) -> None:
        await self._session.execute(
            delete(interview_stage_tasks).where(
                interview_stage_tasks.c.stage_id == stage_id, interview_stage_tasks.c.task_id == task_id
            )
        )
        await self._session.commit()

    async def list_tasks(self, stage_id: int) -> list[Task]:
        result = await self._session.execute(
            select(Task)
            .join(interview_stage_tasks, interview_stage_tasks.c.task_id == Task.id)
            .where(interview_stage_tasks.c.stage_id == stage_id)
        )
        return list(result.scalars().all())

    # -- stage <-> note association --

    async def link_note(self, stage_id: int, note_id: int) -> None:
        await self._session.execute(interview_stage_notes.insert().values(stage_id=stage_id, note_id=note_id))
        await self._session.commit()

    async def unlink_note(self, stage_id: int, note_id: int) -> None:
        await self._session.execute(
            delete(interview_stage_notes).where(
                interview_stage_notes.c.stage_id == stage_id, interview_stage_notes.c.note_id == note_id
            )
        )
        await self._session.commit()

    async def list_notes(self, stage_id: int) -> list[Note]:
        result = await self._session.execute(
            select(Note)
            .join(interview_stage_notes, interview_stage_notes.c.note_id == Note.id)
            .where(interview_stage_notes.c.stage_id == stage_id)
        )
        return list(result.scalars().all())
