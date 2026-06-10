import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.monitors.repository import (
    get_monitor,
    get_monitors,
    get_active_monitors,
    create_monitor,
    update_monitor,
    delete_monitor,
    create_monitor_log,
    get_monitor_logs,
)
from app.features.monitors.tables import Monitor, MonitorLog
from app.features.monitors.schemas import MonitorCreate, MonitorUpdate


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
        # setattr is called on the monitor mock for each field
        assert monitor.name == "New Name"
        assert monitor.enabled is False


class TestDeleteMonitor:
    async def test_found_deletes_and_commits(self):
        session = _make_session()
        monitor = _make_monitor_orm()

        # First call: get_monitor (first())
        # Second call: DELETE execute
        session.execute.side_effect = [_scalar_first(monitor), MagicMock()]

        result = await delete_monitor(session, monitor_id=1)

        assert result == monitor
        session.commit.assert_called_once()

    async def test_not_found_returns_none(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await delete_monitor(session, monitor_id=999)
        assert result is None


class TestCreateMonitorLog:
    async def test_creates_log_entry(self):
        session = _make_session()
        monitor = _make_monitor_orm()
        check_result = {"found": True, "elements_checked": 5, "error": None}

        log = await create_monitor_log(session, monitor=monitor, result=check_result)

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert log is not None

    async def test_log_reflects_result_data(self):
        session = _make_session()
        monitor = _make_monitor_orm()
        check_result = {"found": False, "elements_checked": 0, "error": "Request failed"}

        log = await create_monitor_log(session, monitor=monitor, result=check_result)

        assert log.found is False
        assert log.elements_checked == 0
        assert log.error == "Request failed"

    async def test_log_reflects_monitor_data(self):
        session = _make_session()
        monitor = _make_monitor_orm(id=42)
        check_result = {"found": True, "elements_checked": 1, "error": None}

        log = await create_monitor_log(session, monitor=monitor, result=check_result)

        assert log.monitor_id == 42
        assert log.url == monitor.url
        assert log.target == monitor.target


class TestGetMonitorLogs:
    async def test_returns_logs(self):
        session = _make_session()
        logs = [MagicMock(spec=MonitorLog) for _ in range(3)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = logs
        session.execute.return_value = result_mock

        result = await get_monitor_logs(session, monitor_id=1, limit=10)
        assert len(result) == 3

    async def test_empty_logs(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        result = await get_monitor_logs(session, monitor_id=1)
        assert result == []
