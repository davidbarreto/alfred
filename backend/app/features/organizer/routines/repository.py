from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.calendar_events.tables import CalendarEvent
from app.features.organizer.notes.tables import Note
from app.features.organizer.routines.schemas import RoutineCreate, RoutineStepBase, RoutineUpdate
from app.features.organizer.routines.tables import Routine, RoutineStep


class RoutineRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_routine(self, routine_id: int) -> Routine | None:
        # populate_existing: sessions keep expire_on_commit off, so a routine loaded earlier in the
        # same request would otherwise keep a stale steps collection after a step is added or removed.
        result = await self._session.execute(
            select(Routine)
            .options(selectinload(Routine.steps))
            .where(Routine.id == routine_id)
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def get_routines(self, active: bool | None = None) -> list[Routine]:
        query = select(Routine).options(selectinload(Routine.steps)).order_by(Routine.name, Routine.id)
        if active is not None:
            query = query.where(Routine.active.is_(active))
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_routines_by_ids(self, routine_ids: list[int]) -> list[Routine]:
        if not routine_ids:
            return []
        result = await self._session.execute(
            select(Routine).options(selectinload(Routine.steps)).where(Routine.id.in_(routine_ids))
        )
        return list(result.scalars().all())

    async def get_active_scheduled_routines(self) -> list[Routine]:
        result = await self._session.execute(
            select(Routine)
            .options(selectinload(Routine.steps))
            .where(Routine.active.is_(True), Routine.recurrence_rule.isnot(None))
            .order_by(Routine.id)
        )
        return list(result.scalars().all())

    async def get_event_ids_by_routine(self, routine_ids: list[int]) -> dict[int, list[int]]:
        if not routine_ids:
            return {}
        result = await self._session.execute(
            select(CalendarEvent.routine_id, CalendarEvent.id)
            .where(CalendarEvent.routine_id.in_(routine_ids))
            .order_by(CalendarEvent.id)
        )
        mapping: dict[int, list[int]] = {}
        for routine_id, event_id in result.all():
            mapping.setdefault(routine_id, []).append(event_id)
        return mapping

    async def create_routine(self, data: RoutineCreate) -> Routine:
        routine = Routine(**data.model_dump())
        self._session.add(routine)
        await self._session.commit()
        return await self._require_routine(routine.id)

    async def update_routine(self, routine_id: int, data: RoutineUpdate) -> Routine | None:
        routine = await self.get_routine(routine_id)
        if routine is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(routine, field, value)
        await self._session.commit()
        return await self._require_routine(routine_id)

    async def delete_routine(self, routine_id: int) -> None:
        await self._session.execute(delete(Routine).where(Routine.id == routine_id))
        await self._session.commit()

    async def _require_routine(self, routine_id: int) -> Routine:
        routine = await self.get_routine(routine_id)
        assert routine is not None
        return routine

    async def get_step(self, step_id: int) -> RoutineStep | None:
        result = await self._session.execute(select(RoutineStep).where(RoutineStep.id == step_id))
        return result.scalars().first()

    async def next_position(self, routine_id: int) -> int:
        result = await self._session.execute(
            select(func.max(RoutineStep.position)).where(RoutineStep.routine_id == routine_id)
        )
        highest = result.scalar()
        return 0 if highest is None else highest + 1

    async def position_taken(self, routine_id: int, position: int, except_step_id: int | None = None) -> bool:
        query = select(RoutineStep.id).where(RoutineStep.routine_id == routine_id, RoutineStep.position == position)
        if except_step_id is not None:
            query = query.where(RoutineStep.id != except_step_id)
        result = await self._session.execute(query)
        return result.first() is not None

    async def create_step(self, routine_id: int, position: int, data: RoutineStepBase) -> RoutineStep:
        step = RoutineStep(routine_id=routine_id, position=position, **data.model_dump())
        self._session.add(step)
        await self._session.commit()
        return step

    async def update_step(self, step: RoutineStep, position: int, data: RoutineStepBase) -> RoutineStep:
        step.position = position
        for field, value in data.model_dump().items():
            setattr(step, field, value)
        await self._session.commit()
        return step

    async def delete_step(self, step_id: int) -> None:
        await self._session.execute(delete(RoutineStep).where(RoutineStep.id == step_id))
        await self._session.commit()

    async def note_exists(self, note_id: int) -> bool:
        result = await self._session.execute(
            select(Note.id).where(Note.id == note_id, Note.deleted_at.is_(None))
        )
        return result.first() is not None

    async def get_notes(self, note_ids: list[int]) -> dict[int, Note]:
        if not note_ids:
            return {}
        result = await self._session.execute(
            select(Note).where(Note.id.in_(note_ids), Note.deleted_at.is_(None))
        )
        return {note.id: note for note in result.scalars().all()}

    async def event_exists(self, event_id: int) -> bool:
        result = await self._session.execute(select(CalendarEvent.id).where(CalendarEvent.id == event_id))
        return result.first() is not None

    async def get_event_routine_id(self, event_id: int) -> int | None:
        result = await self._session.execute(select(CalendarEvent.routine_id).where(CalendarEvent.id == event_id))
        return result.scalar()

    async def set_event_routine(self, event_id: int, routine_id: int | None) -> None:
        await self._session.execute(
            update(CalendarEvent).where(CalendarEvent.id == event_id).values(routine_id=routine_id)
        )
        await self._session.commit()
