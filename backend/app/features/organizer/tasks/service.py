import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.storage import StorageProvider
from app.features.organizer.tasks.tables import Task
from app.features.organizer.tasks.schemas import TaskCreate, TaskUpdate, TaskFilters, TaskRead
from app.features.organizer.tasks.repository import TaskRepository

logger = logging.getLogger(__name__)


class TaskService:
    
    def __init__(self, provider: StorageProvider, session: AsyncSession) -> None:
        self._provider = provider
        self._session = session
        self._repo = TaskRepository(session)

    async def get_task(self, task_id: int) -> TaskRead | None:
        task_orm = await self._repo.get_task(task_id)
        if task_orm is None:
            return None
        return TaskRead.model_validate(task_orm)

    async def get_tasks(self, filters: TaskFilters) -> list[TaskRead]:
        tasks_orm = await self._repo.get_tasks(filters)
        return [TaskRead.model_validate(task_orm) for task_orm in tasks_orm]

    async def create_task(self, task_create: TaskCreate) -> TaskRead:
        task_record = await self._provider.create(task_create.model_dump(), self._session)
        task_orm = await self._repo.create_task(task_create, task_record["id"])
        logger.info("Task created: id=%d title=%r", task_orm.id, task_create.title)
        return TaskRead.model_validate(task_orm)

    async def update_task(
        self, task_id: int, task_update: TaskUpdate
    ) -> TaskRead | None:
        task = await self._repo.get_task(task_id)
        if task is None:
            logger.debug("Task update: id=%d not found", task_id)
            return None
        await self._provider.update(
            task.provider_id,
            task_update.model_dump(exclude_unset=True),
            self._session,
        )
        task_orm = await self._repo.update_task(task_id, task_update)
        logger.info("Task updated: id=%d fields=%s", task_id, list(task_update.model_dump(exclude_unset=True).keys()))
        return TaskRead.model_validate(task_orm)

    async def delete_task(self, task_id: int):
        task = await self._repo.get_task(task_id)
        if task:
            await self._provider.delete(task.provider_id, self._session)
            await self._repo.delete_monitor(task_id)
            logger.info("Task deleted: id=%d", task_id)
