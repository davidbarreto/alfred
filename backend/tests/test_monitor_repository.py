import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.monitoring.repository import (
    get_monitor,
    get_monitors,
    get_active_monitors,
    create_monitor,
    update_monitor,
    delete_monitor,
    create_execution,
    get_executions,
    get_alerts,
    upsert_alert,
)
from app.features.monitoring.tables import Alert, Execution, Monitor
from app.features.monitoring.schemas import MonitorCreate, MonitorUpdate


def _make_session():
    return AsyncMock(spec=AsyncSession)


def _make_monitor_orm(id=1, enabled=True):
    monitor = MagicMock(spec=Monitor)
    monitor.id = id
    monitor.name = "Test Monitor"
    monitor.description = "desc"
    monitor.enabled = enabled
    monitor.type = "html_static"
    monitor.url = "http://example.com"
    monitor.selector = ".content"
    monitor.json_path = None
    monitor.target = "Target"
    monitor.case_sensitive = True
    monitor.timeout = 10
    monitor.page_size = 32
    monitor.max_pages = None
    monitor.request_delay = 0
    monitor.wait_selector = None
    return monitor


def _make_execution_orm(id=1, config_id=1, status="found"):
    execution = MagicMock(spec=Execution)
    execution.id = id
    execution.config_id = config_id
    execution.status = status
    execution.result = "matched text"
    execution.error = None
    execution.config_snapshot = {}
    return execution


def _scalar_first(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


class TestGetMonitor:
    async def test_found(self):
        session = _make_session()
        monitor = _make_monitor_orm()
        session.execute.return_value = _scalar_first(monitor)

        result = await get_monitor(session, monitor_id=1)
        assert result == monitor

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await get_monitor(session, monitor_id=999)
        assert result is None


class TestGetMonitors:
    async def test_returns_all(self):
        session = _make_session()
        monitors = [_make_monitor_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(monitors)

        result = await get_monitors(session)
        assert len(result) == 3

    async def test_empty_list(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        result = await get_monitors(session)
        assert result == []

    async def test_uses_skip_and_limit(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await get_monitors(session, skip=10, limit=5)
        session.execute.assert_called_once()


class TestGetActiveMonitors:
    async def test_returns_enabled_monitors(self):
        session = _make_session()
        monitors = [_make_monitor_orm(enabled=True)]
        session.execute.return_value = _scalar_all(monitors)

        result = await get_active_monitors(session)
        assert len(result) == 1

    async def test_empty(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        result = await get_active_monitors(session)
        assert result == []


class TestCreateMonitor:
    async def test_creates_and_commits(self):
        session = _make_session()

        monitor_create = MonitorCreate(
            name="New Monitor",
            url="http://example.com",
            target="Target",
            type="html_static",
        )

        result = await create_monitor(session, monitor_create)

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result is not None

    async def test_returns_monitor_object(self):
        session = _make_session()
        monitor_create = MonitorCreate(
            name="Monitor",
            url="http://example.com",
            target="Target",
            type="html_static",
        )
        result = await create_monitor(session, monitor_create)
        assert isinstance(result, Monitor)


class TestUpdateMonitor:
    async def test_found_updates_and_commits(self):
        session = _make_session()
        monitor = _make_monitor_orm()
        session.execute.return_value = _scalar_first(monitor)

        result = await update_monitor(session, monitor_id=1, monitor_update=MonitorUpdate(name="Updated"))

        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result == monitor

    async def test_not_found_returns_none(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await update_monitor(session, monitor_id=999, monitor_update=MonitorUpdate())
        assert result is None

    async def test_updates_fields(self):
        session = _make_session()
        monitor = _make_monitor_orm()
        session.execute.return_value = _scalar_first(monitor)

        await update_monitor(
            session, monitor_id=1,
            monitor_update=MonitorUpdate(name="New Name", enabled=False)
        )
        assert monitor.name == "New Name"
        assert monitor.enabled is False


class TestDeleteMonitor:
    async def test_found_deletes_and_commits(self):
        session = _make_session()
        monitor = _make_monitor_orm()

        session.execute.side_effect = [_scalar_first(monitor), MagicMock()]

        result = await delete_monitor(session, monitor_id=1)

        assert result == monitor
        session.commit.assert_called_once()

    async def test_not_found_returns_none(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await delete_monitor(session, monitor_id=999)
        assert result is None


class TestCreateExecution:
    async def test_creates_and_commits(self):
        session = _make_session()
        monitor = _make_monitor_orm()

        execution = await create_execution(
            session, monitor=monitor, status="found", result="matched text", error=None
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert execution is not None

    async def test_snapshot_contains_monitor_fields(self):
        session = _make_session()
        monitor = _make_monitor_orm(id=7)

        execution = await create_execution(
            session, monitor=monitor, status="not_found", result=None, error=None
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.config_id == 7
        assert added_obj.status == "not_found"
        assert added_obj.config_snapshot["url"] == monitor.url
        assert added_obj.config_snapshot["target"] == monitor.target
        assert added_obj.config_snapshot["type"] == monitor.type

    async def test_error_status(self):
        session = _make_session()
        monitor = _make_monitor_orm()

        await create_execution(
            session, monitor=monitor, status="error", result=None, error="Request failed"
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.status == "error"
        assert added_obj.error == "Request failed"
        assert added_obj.result is None


class TestGetExecutions:
    async def test_returns_executions(self):
        session = _make_session()
        executions = [MagicMock(spec=Execution) for _ in range(3)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = executions
        session.execute.return_value = result_mock

        result = await get_executions(session, config_id=1, limit=10)
        assert len(result) == 3

    async def test_empty(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        result = await get_executions(session, config_id=1)
        assert result == []


class TestGetAlerts:
    async def test_returns_alerts(self):
        session = _make_session()
        alerts = [MagicMock(spec=Alert) for _ in range(3)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = alerts
        session.execute.return_value = result_mock

        result = await get_alerts(session)
        assert len(result) == 3

    async def test_empty(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        result = await get_alerts(session)
        assert result == []

    async def test_passes_filters_without_error(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        result = await get_alerts(session, status="pending", config_id=1, skip=0, limit=5)
        session.execute.assert_called_once()
        assert result == []


class TestUpsertAlert:
    async def test_creates_alert_when_none_exists(self):
        session = _make_session()
        execution = _make_execution_orm(id=10, config_id=1)
        # _get_latest_alert_for_monitor returns None → create new
        session.execute.return_value = _scalar_first(None)

        alert = await upsert_alert(session, execution=execution)

        session.add.assert_called_once()
        session.commit.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.execution_id == 10
        assert added.status == "pending"

    async def test_does_nothing_when_pending_exists(self):
        session = _make_session()
        execution = _make_execution_orm(id=11, config_id=1)
        existing = MagicMock(spec=Alert)
        existing.status = "pending"
        session.execute.return_value = _scalar_first(existing)

        alert = await upsert_alert(session, execution=execution)

        session.add.assert_not_called()
        session.commit.assert_not_called()
        assert alert is existing

    async def test_reopens_done_alert(self):
        session = _make_session()
        execution = _make_execution_orm(id=12, config_id=1)
        existing = MagicMock(spec=Alert)
        existing.status = "done"
        session.execute.return_value = _scalar_first(existing)

        await upsert_alert(session, execution=execution)

        assert existing.status == "pending"
        assert existing.execution_id == 12
        assert existing.resolved_at is None
        session.commit.assert_called_once()
