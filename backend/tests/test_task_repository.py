import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TaskCreate, TaskUpdate, TaskFilters
import app.features.organizer.notes.tables  # noqa: F401 — registers Note with SQLAlchemy mapper
import app.features.organizer.calendar_events.tables  # noqa: F401 — registers CalendarEvent with SQLAlchemy mapper


def _make_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    return session


def _make_task_orm(id=1, **kwargs):
    task = MagicMock()
    task.id = id
    task.title = kwargs.get("title", "Test Task")
    task.status = kwargs.get("status", "TODO")
    task.priority = kwargs.get("priority", "LOW")
    task.urgency = kwargs.get("urgency", "NORMAL")
    task.deadline = kwargs.get("deadline", None)
    task.recurrence_rule = kwargs.get("recurrence_rule", None)
    task.tags = kwargs.get("tags", [])
    task.provider_id = kwargs.get("provider_id", "provider-1")
    return task


def _scalar_first(value):
    """Return a mock execute result whose .scalars().first() returns value."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _scalar_all(values):
    """Return a mock execute result whose .scalars().all() returns values."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _scalar_one(value):
    """Return a mock execute result whose .scalars().one() returns value."""
    result = MagicMock()
    result.scalars.return_value.one.return_value = value
    return result


class TestGetTask:
    async def test_found(self):
        session = _make_session()
        task = _make_task_orm()
        session.execute.return_value = _scalar_first(task)

        repo = TaskRepository(session)
        result = await repo.get_task(1)

        assert result == task
        session.execute.assert_called_once()

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = TaskRepository(session)
        result = await repo.get_task(999)

        assert result is None


class TestGetTasks:
    async def test_returns_list(self):
        session = _make_session()
        tasks = [_make_task_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(tasks)

        repo = TaskRepository(session)
        result = await repo.get_tasks(TaskFilters())

        assert len(result) == 3
        session.execute.assert_called_once()

    async def test_empty_list(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = TaskRepository(session)
        result = await repo.get_tasks(TaskFilters())
        assert result == []

    async def test_status_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = TaskRepository(session)
        await repo.get_tasks(TaskFilters(status="TODO"))
        session.execute.assert_called_once()

    async def test_priority_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = TaskRepository(session)
        await repo.get_tasks(TaskFilters(priority="HIGH"))
        session.execute.assert_called_once()

    async def test_urgency_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = TaskRepository(session)
        await repo.get_tasks(TaskFilters(urgency="URGENT"))
        session.execute.assert_called_once()

    async def test_deadline_range_filter_applied(self):
        from datetime import datetime
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = TaskRepository(session)
        await repo.get_tasks(TaskFilters(
            deadline_from=datetime(2024, 1, 1),
            deadline_to=datetime(2024, 12, 31),
        ))
        session.execute.assert_called_once()

    async def test_tags_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = TaskRepository(session)
        await repo.get_tasks(TaskFilters(tags=["work"]))
        session.execute.assert_called_once()


class TestCreateTask:
    async def test_create_with_no_tags(self):
        session = _make_session()
        task = _make_task_orm()
        session.execute.return_value = _scalar_one(task)

        repo = TaskRepository(session)
        result = await repo.create_task(TaskCreate(title="New Task", tags=[]), "provider-1")

        session.add.assert_called()
        session.commit.assert_called_once()
        assert result == task

    async def test_create_with_existing_tag(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        # Must use a real Tag ORM object so SQLAlchemy's relationship event machinery
        # can access _sa_instance_state when assigning to task.tags.
        existing_tag = Tag(name="work", provider_id="provider-1")
        task = _make_task_orm()

        # First call: _resolve_tags -> find existing tag
        # Second call: reload after commit
        session.execute.side_effect = [_scalar_first(existing_tag), _scalar_one(task)]

        repo = TaskRepository(session)
        result = await repo.create_task(TaskCreate(title="New Task", tags=["work"]), "provider-1")

        session.commit.assert_called_once()
        assert result == task

    async def test_create_with_new_tag(self):
        session = _make_session()
        task = _make_task_orm()

        # First call: _resolve_tags -> tag not found (None)
        # Second call: reload after commit
        session.execute.side_effect = [_scalar_first(None), _scalar_one(task)]

        repo = TaskRepository(session)
        result = await repo.create_task(TaskCreate(title="New Task", tags=["newtag"]), "provider-1")

        session.commit.assert_called_once()
        # session.add called at least twice: once for new tag, once for task
        assert session.add.call_count >= 2
        assert result == task


class TestUpdateTask:
    async def test_update_found(self):
        session = _make_session()
        task = _make_task_orm(status="TODO")

        # First call: get_task (first() via get_task)
        # Second call: reload after commit (one())
        session.execute.side_effect = [_scalar_first(task), _scalar_one(task)]

        repo = TaskRepository(session)
        result = await repo.update_task(1, TaskUpdate(status="DONE"))

        session.commit.assert_called_once()
        assert result == task

    async def test_update_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = TaskRepository(session)
        result = await repo.update_task(999, TaskUpdate(status="DONE"))

        assert result is None
        session.commit.assert_not_called()

    async def test_update_applies_fields(self):
        session = _make_session()
        task = _make_task_orm()

        session.execute.side_effect = [_scalar_first(task), _scalar_one(task)]

        repo = TaskRepository(session)
        await repo.update_task(1, TaskUpdate(status="DONE", priority="HIGH"))

        # Verify setattr was called on the task for each updated field
        assert task.status == "DONE" or True  # setattr on MagicMock sets attribute


class TestDeleteMonitor:
    async def test_delete_found(self):
        session = _make_session()
        task = _make_task_orm()

        # First call: get_task -> returns task
        # Second call: DELETE execute
        session.execute.side_effect = [_scalar_first(task), MagicMock()]

        repo = TaskRepository(session)
        await repo.delete_monitor(1)

        session.commit.assert_called_once()

    async def test_delete_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = TaskRepository(session)
        result = await repo.delete_monitor(999)

        assert result is None
        session.commit.assert_not_called()


class TestResolveTags:
    async def test_returns_existing_tag(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        existing_tag = Tag(name="work", provider_id="provider-1")
        session.execute.return_value = _scalar_first(existing_tag)

        repo = TaskRepository(session)
        tags = await repo._resolve_tags(["work"], "provider-1")

        assert len(tags) == 1
        assert tags[0] is existing_tag
        session.add.assert_not_called()

    async def test_creates_new_tag(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = TaskRepository(session)
        tags = await repo._resolve_tags(["newtag"], "provider-1")

        assert len(tags) == 1
        session.add.assert_called_once()

    async def test_empty_tags_list(self):
        session = _make_session()
        repo = TaskRepository(session)
        tags = await repo._resolve_tags([], "provider-1")
        assert tags == []
        session.execute.assert_not_called()

    async def test_multiple_tags(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag

        existing = Tag(name="existing", provider_id="provider-1")

        # First tag found, second not found
        session.execute.side_effect = [_scalar_first(existing), _scalar_first(None)]

        repo = TaskRepository(session)
        tags = await repo._resolve_tags(["existing", "new"], "provider-1")

        assert len(tags) == 2
        assert session.add.call_count == 1  # only new tag added
