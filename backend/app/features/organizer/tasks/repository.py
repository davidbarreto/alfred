from datetime import date, datetime, timezone
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.tags.tables import Tag
from app.features.organizer.tasks.tables import Task, TaskCompletion
from app.features.organizer.tasks.schemas import TaskCreate, TaskUpdate, TaskFilters

_TASK_EXCLUDE = {"tags"}


class TaskRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_task(self, task_id: int) -> Task | None:
        result = await self._session.execute(
            select(Task)
            .options(selectinload(Task.tags))
            .where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def get_tasks(self, task_filter: TaskFilters) -> list[Task]:
        query = select(Task).options(selectinload(Task.tags)).where(Task.deleted_at.is_(None))
        if task_filter.status != "ALL":
            query = query.where(Task.status == task_filter.status)
        if task_filter.priority != "ALL":
            query = query.where(Task.priority == task_filter.priority)
        if task_filter.urgency != "ALL":
            query = query.where(Task.urgency == task_filter.urgency)
        has_deadline_filter = task_filter.deadline_from is not None or task_filter.deadline_to is not None
        if has_deadline_filter:
            deadline_clauses = []
            if task_filter.deadline_from is not None:
                deadline_clauses.append(Task.deadline >= task_filter.deadline_from)
            if task_filter.deadline_to is not None:
                deadline_clauses.append(Task.deadline <= task_filter.deadline_to)
            deadline_cond = and_(*deadline_clauses)
            if task_filter.include_recurring:
                query = query.where(or_(deadline_cond, Task.recurrence_rule.is_not(None)))
            else:
                query = query.where(deadline_cond)
        if task_filter.tags:
            query = query.where(Task.tags.any(Tag.name.in_(task_filter.tags)))
        query = query.limit(task_filter.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _resolve_tags(self, tag_names: list[str], provider_id: str) -> list[Tag]:
        tags = []
        for name in tag_names:
            result = await self._session.execute(
                select(Tag).where(Tag.provider_id == provider_id, Tag.name == name)
            )
            tag = result.scalars().first()
            if tag is None:
                tag = Tag(provider_id=provider_id, name=name)
                self._session.add(tag)
            tags.append(tag)
        return tags

    async def create_task(self, task_create: TaskCreate, provider_id: str) -> Task:
        task = Task(**task_create.model_dump(exclude=_TASK_EXCLUDE), provider_id=provider_id)
        task.tags = await self._resolve_tags(task_create.tags, provider_id)
        self._session.add(task)
        await self._session.commit()
        result = await self._session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id == task.id)
        )
        return result.scalars().one()

    async def update_task(self, task_id: int, task_update: TaskUpdate) -> Task | None:
        task = await self.get_task(task_id)
        if task is None:
            return None

        for field, value in task_update.model_dump(exclude_unset=True).items():
            setattr(task, field, value)

        await self._session.commit()
        result = await self._session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id == task_id)
        )
        return result.scalars().one()

    async def delete_task(self, task_id: int) -> None:
        await self._session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
        await self._session.commit()

    async def get_completed_task_ids_for_date(self, task_ids: list[int], for_date: date) -> set[int]:
        if not task_ids:
            return set()
        result = await self._session.execute(
            select(TaskCompletion.task_id).where(
                TaskCompletion.task_id.in_(task_ids),
                TaskCompletion.occurrence_date == for_date,
            )
        )
        return set(result.scalars().all())

    async def get_completion(self, task_id: int, occurrence_date: date) -> TaskCompletion | None:
        result = await self._session.execute(
            select(TaskCompletion).where(
                TaskCompletion.task_id == task_id,
                TaskCompletion.occurrence_date == occurrence_date,
            )
        )
        return result.scalars().first()

    async def get_completions_by_task(self, task_ids: list[int]) -> dict[int, list[date]]:
        if not task_ids:
            return {}
        result = await self._session.execute(
            select(TaskCompletion.task_id, TaskCompletion.occurrence_date)
            .where(TaskCompletion.task_id.in_(task_ids))
            .order_by(TaskCompletion.occurrence_date.desc())
        )
        completions: dict[int, list[date]] = {tid: [] for tid in task_ids}
        for task_id, occ_date in result.all():
            completions[task_id].append(occ_date)
        return completions

    async def get_task_completions(self, task_id: int) -> list[TaskCompletion]:
        result = await self._session.execute(
            select(TaskCompletion)
            .where(TaskCompletion.task_id == task_id)
            .order_by(TaskCompletion.occurrence_date.desc())
        )
        return list(result.scalars().all())

    async def complete_occurrence(self, task_id: int, occurrence_date: date) -> TaskCompletion:
        completion = TaskCompletion(task_id=task_id, occurrence_date=occurrence_date)
        self._session.add(completion)
        await self._session.commit()
        await self._session.refresh(completion)
        return completion
