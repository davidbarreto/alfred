import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.features.watcher.repository import (
    get_watcher,
    get_watchers,
    get_active_watchers,
    create_watcher,
    update_watcher,
    delete_watcher,
    create_execution,
    get_executions,
    get_alerts,
    upsert_alert,
    get_pending_alerts_with_context,
    resolve_alerts,
)
from app.features.watcher.tables import Alert, Execution, Watcher
from app.features.watcher.schemas import WatcherCreate, WatcherUpdate


def _make_session():
    return AsyncMock(spec=AsyncSession)


def _make_watcher_orm(id=1, enabled=True):
    watcher = MagicMock(spec=Watcher)
    watcher.id = id
    watcher.name = "Test Watcher"
    watcher.description = "desc"
    watcher.enabled = enabled
    watcher.type = "html_static"
    watcher.url = "http://example.com"
    watcher.selector = ".content"
    watcher.json_path = None
    watcher.target = "Target"
    watcher.case_sensitive = True
    watcher.timeout = 10
    watcher.page_size = 32
    watcher.max_pages = None
    watcher.request_delay = 0
    watcher.wait_selector = None
    return watcher


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


class TestGetWatcher:
    async def test_found(self):
        session = _make_session()
        watcher = _make_watcher_orm()
        session.execute.return_value = _scalar_first(watcher)

        result = await get_watcher(session, watcher_id=1)
        assert result == watcher

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await get_watcher(session, watcher_id=999)
        assert result is None


class TestGetWatchers:
    async def test_returns_all(self):
        session = _make_session()
        monitors = [_make_watcher_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(monitors)

        result = await get_watchers(session)
        assert len(result) == 3

    async def test_empty_list(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        result = await get_watchers(session)
        assert result == []

    async def test_uses_skip_and_limit(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await get_watchers(session, skip=10, limit=5)
        session.execute.assert_called_once()


class TestGetActiveWatchers:
    async def test_returns_enabled_monitors(self):
        session = _make_session()
        monitors = [_make_watcher_orm(enabled=True)]
        session.execute.return_value = _scalar_all(monitors)

        result = await get_active_watchers(session)
        assert len(result) == 1

    async def test_empty(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        result = await get_active_watchers(session)
        assert result == []


class TestCreateWatcher:
    async def test_creates_and_commits(self):
        session = _make_session()

        monitor_create = WatcherCreate(
            name="New Monitor",
            url="http://example.com",
            target="Target",
            type="html_static",
        )

        result = await create_watcher(session, monitor_create)

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result is not None

    async def test_returns_monitor_object(self):
        session = _make_session()
        monitor_create = WatcherCreate(
            name="Monitor",
            url="http://example.com",
            target="Target",
            type="html_static",
        )
        result = await create_watcher(session, monitor_create)
        assert isinstance(result, Watcher)


class TestUpdateWatcher:
    async def test_found_updates_and_commits(self):
        session = _make_session()
        monitor = _make_watcher_orm()
        session.execute.return_value = _scalar_first(monitor)

        result = await update_watcher(session, watcher_id=1, watcher_update=WatcherUpdate(name="Updated"))

        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result == monitor

    async def test_not_found_returns_none(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await update_watcher(session, watcher_id=999, watcher_update=WatcherUpdate())
        assert result is None

    async def test_updates_fields(self):
        session = _make_session()
        monitor = _make_watcher_orm()
        session.execute.return_value = _scalar_first(monitor)

        await update_watcher(
            session, watcher_id=1,
            watcher_update=WatcherUpdate(name="New Name", enabled=False)
        )
        assert monitor.name == "New Name"
        assert monitor.enabled is False


class TestDeleteWatcher:
    async def test_found_deletes_and_commits(self):
        session = _make_session()
        monitor = _make_watcher_orm()

        session.execute.side_effect = [_scalar_first(monitor), MagicMock()]

        result = await delete_watcher(session, watcher_id=1)

        assert result == monitor
        session.commit.assert_called_once()

    async def test_not_found_returns_none(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await delete_watcher(session, watcher_id=999)
        assert result is None


class TestCreateExecution:
    async def test_creates_and_commits(self):
        session = _make_session()
        monitor = _make_watcher_orm()

        execution = await create_execution(
            session, watcher=monitor, status="found", result="matched text", error=None
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert execution is not None

    async def test_snapshot_contains_monitor_fields(self):
        session = _make_session()
        monitor = _make_watcher_orm(id=7)

        execution = await create_execution(
            session, watcher=monitor, status="not_found", result=None, error=None
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.config_id == 7
        assert added_obj.status == "not_found"
        assert added_obj.config_snapshot["url"] == monitor.url
        assert added_obj.config_snapshot["target"] == monitor.target
        assert added_obj.config_snapshot["type"] == monitor.type

    async def test_error_status(self):
        session = _make_session()
        monitor = _make_watcher_orm()

        await create_execution(
            session, watcher=monitor, status="error", result=None, error="Request failed"
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


class TestGetPendingAlertsWithContext:
    async def test_returns_pending_alerts(self):
        session = _make_session()
        alerts = [MagicMock(spec=Alert) for _ in range(2)]
        session.execute.return_value = _scalar_all(alerts)

        result = await get_pending_alerts_with_context(session)
        assert result == alerts

    async def test_empty(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        result = await get_pending_alerts_with_context(session)
        assert result == []


class TestResolveAlerts:
    async def test_updates_status_and_commits(self):
        session = _make_session()
        resolved = [MagicMock(spec=Alert, id=1), MagicMock(spec=Alert, id=2)]
        session.execute.side_effect = [MagicMock(), _scalar_all(resolved)]

        result = await resolve_alerts(session, alert_ids=[1, 2])

        assert session.execute.call_count == 2
        session.commit.assert_called_once()
        assert result == resolved

    async def test_empty_ids_returns_empty(self):
        session = _make_session()
        session.execute.side_effect = [MagicMock(), _scalar_all([])]

        result = await resolve_alerts(session, alert_ids=[])
        assert result == []
