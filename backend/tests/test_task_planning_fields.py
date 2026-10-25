from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.commands.handlers.task import handle_task
from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.assistant.intents.extraction_service import CreateTaskArgs
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TASK_CONTEXTS, TaskCreate, TaskFilters, TaskRead, TaskUpdate
from app.features.organizer.tasks.service import TaskService
from app.features.organizer.tasks.tables import Task
import app.features.organizer.notes.tables  # noqa: F401 — registers Note with SQLAlchemy mapper
import app.features.organizer.calendar_events.tables  # noqa: F401 — registers CalendarEvent with SQLAlchemy mapper


def _task_orm(**kwargs) -> MagicMock:
    task = MagicMock()
    defaults = dict(
        id=1, title="Task", status="TODO", priority="LOW", urgency="NORMAL", deadline=None,
        recurrence_rule=None, tags=[], provider_id="provider-1", estimate_minutes=None, context=None,
        available_from=None,
    )
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(task, key, value)
    return task


@pytest.fixture
def service():
    svc = TaskService(provider=AsyncMock(), session=AsyncMock())
    svc._repo = AsyncMock()
    svc._repo.get_task.return_value = _task_orm()
    svc._repo.update_task.return_value = _task_orm()
    svc._repo.create_task.return_value = _task_orm()
    svc._provider.create.return_value = {"id": "provider-1"}
    return svc


class TestSchemas:
    def test_contexts_are_the_documented_set(self):
        assert TASK_CONTEXTS == ("computer", "phone", "home", "out", "anywhere")

    def test_create_accepts_planning_fields(self):
        task = TaskCreate(title="Buy tickets", estimate_minutes=10, context="phone",
                          available_from=datetime(2026, 10, 24, 0, 0))
        assert task.estimate_minutes == 10
        assert task.context == "phone"

    def test_planning_fields_default_to_none(self):
        task = TaskCreate(title="Buy tickets")
        assert (task.estimate_minutes, task.context, task.available_from) == (None, None, None)

    @pytest.mark.parametrize("minutes", [0, -5])
    def test_estimate_must_be_positive(self, minutes):
        with pytest.raises(ValidationError):
            TaskCreate(title="x", estimate_minutes=minutes)
        with pytest.raises(ValidationError):
            TaskUpdate(estimate_minutes=minutes)

    def test_context_must_be_known(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="x", context="office")

    def test_read_exposes_planning_fields(self):
        read = TaskRead.model_validate(_task_orm(estimate_minutes=30, context="home", created_at=datetime(2026, 10, 1)))
        assert read.estimate_minutes == 30
        assert read.context == "home"


class TestTableConstraints:
    def test_check_constraints_declared(self):
        names = {c.name for c in Task.__table__.constraints if c.name}
        assert {"ck_tasks_estimate_minutes_positive", "ck_tasks_context"} <= names

    def test_context_check_lists_every_value(self):
        check = next(c for c in Task.__table__.constraints if c.name == "ck_tasks_context")
        for value in TASK_CONTEXTS:
            assert f"'{value}'" in str(check.sqltext)


class TestServiceKeepsFieldsAwayFromProvider:
    async def test_create_does_not_send_planning_fields(self, service):
        await service.create_task(TaskCreate(title="Buy", estimate_minutes=10, context="phone",
                                             available_from=datetime(2026, 10, 24)))

        record = service._provider.create.call_args.args[0]
        assert record["title"] == "Buy"
        assert not {"estimate_minutes", "context", "available_from"} & set(record)

    async def test_create_still_persists_planning_fields_locally(self, service):
        payload = TaskCreate(title="Buy", estimate_minutes=10, context="phone")
        await service.create_task(payload)

        assert service._repo.create_task.call_args.args[0] == payload

    async def test_update_mixed_fields_sends_only_provider_fields(self, service):
        await service.update_task(1, TaskUpdate(title="New", estimate_minutes=20, context="home"))

        sent = service._provider.update.call_args.args[1]
        assert sent == {"title": "New"}
        assert service._repo.update_task.call_args.args[1].estimate_minutes == 20

    async def test_update_of_only_planning_fields_makes_no_provider_call(self, service):
        await service.update_task(1, TaskUpdate(estimate_minutes=20, available_from=datetime(2026, 10, 24)))

        service._provider.update.assert_not_called()
        service._repo.update_task.assert_awaited_once()

    async def test_clearing_a_planning_field_is_persisted_without_provider_call(self, service):
        await service.update_task(1, TaskUpdate(context=None))

        service._provider.update.assert_not_called()
        assert service._repo.update_task.call_args.args[1].model_dump(exclude_unset=True) == {"context": None}


class TestHandler:
    @pytest.fixture
    def mock_service(self):
        svc = AsyncMock()
        svc.get_tasks = AsyncMock(return_value=[])
        svc.create_task = AsyncMock(return_value=MagicMock(model_dump=lambda mode: {}))
        svc.update_task = AsyncMock(return_value=MagicMock(model_dump=lambda mode: {}))
        return svc

    async def test_add_parses_planning_fields(self, mock_service):
        await handle_task(
            "add",
            {"title": "Buy tickets", "estimate": "10", "context": "Phone", "available_from": "2026-10-24"},
            mock_service,
        )
        payload = mock_service.create_task.call_args.args[0]
        assert payload.estimate_minutes == 10
        assert payload.context == "phone"
        assert payload.available_from == datetime(2026, 10, 24)

    async def test_add_without_planning_fields_leaves_them_null(self, mock_service):
        await handle_task("add", {"title": "Plain"}, mock_service)
        payload = mock_service.create_task.call_args.args[0]
        assert (payload.estimate_minutes, payload.context, payload.available_from) == (None, None, None)

    async def test_update_sets_only_given_planning_fields(self, mock_service):
        await handle_task("update", {"id": "3", "estimate": "45"}, mock_service)
        assert mock_service.update_task.call_args.args[1] == TaskUpdate(estimate_minutes=45)

    async def test_update_can_clear_a_field_with_empty_value(self, mock_service):
        await handle_task("update", {"id": "3", "context": ""}, mock_service)
        assert mock_service.update_task.call_args.args[1] == TaskUpdate(context=None)

    async def test_update_rejects_unknown_context_with_400(self, mock_service):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await handle_task("update", {"id": "3", "context": "office"}, mock_service)
        assert exc.value.status_code == 400
        assert "computer" in exc.value.detail

    async def test_non_numeric_estimate_is_a_400(self, mock_service):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await handle_task("add", {"title": "x", "estimate": "soon"}, mock_service)
        assert exc.value.status_code == 400

    async def test_list_passes_context_and_available_filters(self, mock_service):
        await handle_task("list", {"context": "phone", "available": "true"}, mock_service)
        filters = mock_service.get_tasks.call_args.args[0]
        assert filters.context == "phone"
        assert filters.available is True

    async def test_list_defaults_do_not_filter_on_planning_fields(self, mock_service):
        await handle_task("list", {}, mock_service)
        filters = mock_service.get_tasks.call_args.args[0]
        assert filters.context is None
        assert filters.available is False


class TestRepositoryFilters:
    @staticmethod
    async def _sql(filters: TaskFilters) -> str:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        await TaskRepository(session).get_tasks(filters)
        statement = session.execute.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        return sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]

    async def test_context_filter(self):
        sql = await self._sql(TaskFilters(context="phone"))
        assert "tasks.context = 'phone'" in sql

    @freeze_time("2026-10-21 12:00:00")
    async def test_available_filter_compares_against_the_current_instant(self):
        sql = await self._sql(TaskFilters(available=True))
        assert "tasks.available_from IS NULL" in sql
        assert "tasks.available_from <= '2026-10-21 12:00:00+00:00'" in sql

    async def test_no_planning_filter_by_default(self):
        sql = await self._sql(TaskFilters())
        assert "context" not in sql
        assert "available_from" not in sql


class TestRegistryAndExtraction:
    def test_add_flags_include_planning_fields(self):
        keys = set(COMMAND_DEFINITIONS["task"]["add"]["flags"].values())
        assert {"estimate", "context", "available_from"} <= keys

    def test_update_and_list_flags(self):
        assert {"estimate", "context", "available_from"} <= set(COMMAND_DEFINITIONS["task"]["update"]["flags"].values())
        assert {"context", "available"} <= set(COMMAND_DEFINITIONS["task"]["list"]["flags"].values())

    def test_details_name_every_enum_value_and_the_unit(self):
        for action in ("add", "update", "list"):
            details = COMMAND_DEFINITIONS["task"][action]["details"]
            for value in TASK_CONTEXTS:
                assert value in details
        add_details = COMMAND_DEFINITIONS["task"]["add"]["details"]
        assert "minutes" in add_details
        assert "not before" in add_details
        assert "ask" in add_details.lower()

    def test_extraction_schema_field_names_match_handler_keys(self):
        fields = CreateTaskArgs.model_fields
        assert {"estimate", "context", "available_from"} <= set(fields)
        assert CreateTaskArgs(title="Buy flixbus tickets", estimate=10, context="phone").context == "phone"
