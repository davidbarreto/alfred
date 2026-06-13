import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.provider_calls.repository import create_sync_log, get_sync_log, get_sync_logs
from app.integrations.provider_calls.tables import IntegrationSyncLog


def _make_session():
    return AsyncMock(spec=AsyncSession)


def _make_log_orm(**kwargs):
    log = MagicMock(spec=IntegrationSyncLog)
    log.id = kwargs.get("id", 1)
    log.provider = kwargs.get("provider", "notion")
    log.operation = kwargs.get("operation", "create")
    log.entity_type = kwargs.get("entity_type", "task")
    log.provider_entity_id = kwargs.get("provider_entity_id", "page-123")
    log.status = kwargs.get("status", "ok")
    log.request_payload = kwargs.get("request_payload", {"properties": {}})
    log.response_payload = kwargs.get("response_payload", {"id": "page-123"})
    log.error = kwargs.get("error", None)
    return log


class TestCreateSyncLog:
    async def test_adds_log_to_session(self):
        session = _make_session()
        await create_sync_log(
            session,
            provider="notion",
            operation="create",
            entity_type="task",
            provider_entity_id="page-1",
            status="ok",
            request_payload={"properties": {}},
            response_payload={"id": "page-1"},
            error=None,
        )
        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, IntegrationSyncLog)
        assert added.provider == "notion"
        assert added.operation == "create"
        assert added.entity_type == "task"
        assert added.provider_entity_id == "page-1"
        assert added.status == "ok"
        assert added.error is None

    async def test_error_status_stored(self):
        session = _make_session()
        await create_sync_log(
            session,
            provider="notion",
            operation="update",
            entity_type="note",
            provider_entity_id="page-2",
            status="error",
            request_payload=None,
            response_payload=None,
            error="HTTP 404",
        )
        added = session.add.call_args.args[0]
        assert added.status == "error"
        assert added.error == "HTTP 404"

    async def test_returns_log_instance(self):
        session = _make_session()
        result = await create_sync_log(
            session,
            provider="google_calendar",
            operation="create",
            entity_type="calendar_event",
            provider_entity_id="evt-1",
            status="ok",
            request_payload={},
            response_payload={},
            error=None,
        )
        assert isinstance(result, IntegrationSyncLog)


class TestGetSyncLogs:
    async def test_applies_provider_filter(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await get_sync_logs(session, provider="notion")

        session.execute.assert_called_once()

    async def test_applies_operation_filter(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await get_sync_logs(session, operation="create")

        session.execute.assert_called_once()

    async def test_applies_q_filter(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await get_sync_logs(session, q="timeout")

        session.execute.assert_called_once()

    async def test_applies_after_filter(self):
        from datetime import datetime, timezone
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await get_sync_logs(session, after=datetime(2026, 6, 1, tzinfo=timezone.utc))

        session.execute.assert_called_once()

    async def test_applies_before_filter(self):
        from datetime import datetime, timezone
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await get_sync_logs(session, before=datetime(2026, 6, 12, tzinfo=timezone.utc))

        session.execute.assert_called_once()

    async def test_returns_list(self):
        session = _make_session()
        log = _make_log_orm()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log]
        session.execute.return_value = mock_result

        result = await get_sync_logs(session)

        assert result == [log]

    async def test_no_filters_returns_all(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await get_sync_logs(session)

        session.execute.assert_called_once()


class TestGetSyncLog:
    async def test_returns_log_when_found(self):
        session = _make_session()
        log = _make_log_orm(id=42)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = log
        session.execute.return_value = mock_result

        result = await get_sync_log(session, 42)

        assert result is log

    async def test_returns_none_when_not_found(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute.return_value = mock_result

        result = await get_sync_log(session, 99)

        assert result is None
