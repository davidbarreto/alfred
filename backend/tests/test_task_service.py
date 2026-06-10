import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.features.organizer.tasks.service import TaskService
from app.features.organizer.tasks.schemas import TaskCreate, TaskUpdate, TaskFilters, TaskRead


def _make_task_read(**kwargs):
    defaults = dict(
        id=1, title="Test Task", status="TODO",
        priority="LOW", urgency="NORMAL", tags=[],
        deadline=None, recurrence_rule=None,
    )
    defaults.update(kwargs)
    return TaskRead(**defaults)


def _make_task_orm(**kwargs):
    task = MagicMock()
    task.id = kwargs.get("id", 1)
    task.title = kwargs.get("title", "Test Task")
    task.status = kwargs.get("status", "TODO")
    task.priority = kwargs.get("priority", "LOW")
    task.urgency = kwargs.get("urgency", "NORMAL")
    task.deadline = kwargs.get("deadline", None)
    task.recurrence_rule = kwargs.get("recurrence_rule", None)
    task.tags = kwargs.get("tags", [])
    task.provider_id = kwargs.get("provider_id", "provider-1")
    return task


@pytest.fixture
def mock_provider():
    return AsyncMock()


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_provider, mock_session):
    svc = TaskService(provider=mock_provider, session=mock_session)
    svc._repo = AsyncMock()
    return svc


class TestGetTask:
    async def test_returns_task_read_when_found(self, service):
        task_orm = _make_task_orm()
        service._repo.get_task.return_value = task_orm

        result = await service.get_task(1)

        service._repo.get_task.assert_called_once_with(1)
        assert result is not None
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_task.return_value = None

        result = await service.get_task(999)
        assert result is None

    async def test_returns_task_read_type(self, service):
        service._repo.get_task.return_value = _make_task_orm()
        result = await service.get_task(1)
        assert isinstance(result, TaskRead)


class TestGetTasks:
    async def test_returns_list_of_task_reads(self, service):
        service._repo.get_tasks.return_value = [_make_task_orm(id=i) for i in range(3)]

        result = await service.get_tasks(TaskFilters())

        assert len(result) == 3
        assert all(isinstance(t, TaskRead) for t in result)

    async def test_empty_list(self, service):
        service._repo.get_tasks.return_value = []
        result = await service.get_tasks(TaskFilters())
        assert result == []

    async def test_passes_filters_to_repo(self, service):
        service._repo.get_tasks.return_value = []
        filters = TaskFilters(status="TODO", priority="HIGH")
        await service.get_tasks(filters)
        service._repo.get_tasks.assert_called_once_with(filters)


class TestCreateTask:
    async def test_calls_provider_create(self, service, mock_provider):
        task_create = TaskCreate(title="New Task")
        mock_provider.create.return_value = {"id": "provider-abc"}
        service._repo.create_task.return_value = _make_task_orm(title="New Task")

        await service.create_task(task_create)

        mock_provider.create.assert_called_once()

    async def test_calls_repo_create_with_provider_id(self, service, mock_provider):
        task_create = TaskCreate(title="New Task")
        mock_provider.create.return_value = {"id": "provider-xyz"}
        service._repo.create_task.return_value = _make_task_orm()

        await service.create_task(task_create)

        service._repo.create_task.assert_called_once_with(task_create, "provider-xyz")

    async def test_returns_task_read(self, service, mock_provider):
        mock_provider.create.return_value = {"id": "provider-1"}
        service._repo.create_task.return_value = _make_task_orm()

        result = await service.create_task(TaskCreate(title="Test"))
        assert isinstance(result, TaskRead)


class TestUpdateTask:
    async def test_returns_updated_task(self, service):
        service._repo.update_task.return_value = _make_task_orm(status="DONE")
        task_update = TaskUpdate(status="DONE")

        result = await service.update_task(1, task_update)

        service._repo.update_task.assert_called_once_with(1, task_update)
        assert isinstance(result, TaskRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_task.return_value = None
        result = await service.update_task(999, TaskUpdate(status="DONE"))
        assert result is None


class TestDeleteTask:
    async def test_calls_delete_when_found(self, service):
        service._repo.get_task.return_value = _make_task_orm()

        await service.delete_task(1)

        service._repo.delete_monitor.assert_called_once_with(1)

    async def test_does_not_call_delete_when_not_found(self, service):
        service._repo.get_task.return_value = None

        await service.delete_task(999)

        service._repo.delete_monitor.assert_not_called()
