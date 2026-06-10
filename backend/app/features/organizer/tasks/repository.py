from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.tags.tables import Tag
from app.features.organizer.tasks.tables import Task
from app.features.organizer.tasks.schemas import TaskCreate, TaskUpdate, TaskFilters

_TASK_EXCLUDE = {"tags"}

class TaskRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_task(self, task_id: int) -> Task | None:
        result = await self._session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id == task_id)
        )
        return result.scalars().first()

    async def get_tasks(self, task_filter: TaskFilters) -> list[Task]:
        query = select(Task).options(selectinload(Task.tags))
        if task_filter.status != "ALL":
            query = query.where(Task.status == task_filter.status)
        if task_filter.priority != "ALL":
            query = query.where(Task.priority == task_filter.priority)
        if task_filter.urgency != "ALL":
            query = query.where(Task.urgency == task_filter.urgency)
        if task_filter.deadline_from is not None:
            query = query.where(Task.deadline >= task_filter.deadline_from)
        if task_filter.deadline_to is not None:
            query = query.where(Task.deadline <= task_filter.deadline_to)
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

    async def update_task(
        self,
        task_id: int,
        task_update: TaskUpdate,
    ) -> Task | None:
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

    async def delete_monitor(self, task_id: int):
        task = await self.get_task(task_id)
        if task is None:
            return None

        await self._session.execute(delete(Task).where(Task.id == task_id))
        await self._session.commit()
