from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.features.core.pause.service import PAUSE_KEY, GlobalPauseService
from app.features.core.pause.schemas import PauseStateRead


@pytest.fixture
def service():
    svc = GlobalPauseService.__new__(GlobalPauseService)
    svc._settings = AsyncMock()
    svc._task_service = AsyncMock()
    return svc


class TestGetState:
    async def test_not_paused_when_unset(self, service):
        service._settings.get_value.return_value = None

        result = await service.get_state()

        service._settings.get_value.assert_called_once_with(PAUSE_KEY)
        assert result == PauseStateRead(paused=False, paused_at=None)

    async def test_not_paused_when_cleared_to_empty_string(self, service):
        service._settings.get_value.return_value = ""

        result = await service.get_state()

        assert result.paused is False

    async def test_paused_when_timestamp_stored(self, service):
        paused_at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        service._settings.get_value.return_value = paused_at.isoformat()

        result = await service.get_state()

        assert result.paused is True
        assert result.paused_at == paused_at


class TestIsPaused:
    async def test_returns_true(self, service):
        service._settings.get_value.return_value = datetime.now(timezone.utc).isoformat()
        assert await service.is_paused() is True

    async def test_returns_false(self, service):
        service._settings.get_value.return_value = None
        assert await service.is_paused() is False


class TestPause:
    async def test_stores_current_timestamp(self, service):
        service._settings.get_value.return_value = None

        result = await service.pause()

        assert result.paused is True
        assert result.paused_at is not None
        service._settings.set_value.assert_called_once()
        key, value = service._settings.set_value.call_args.args
        assert key == PAUSE_KEY
        assert value == result.paused_at.isoformat()

    async def test_rejects_when_already_paused(self, service):
        service._settings.get_value.return_value = datetime.now(timezone.utc).isoformat()

        with pytest.raises(HTTPException) as exc_info:
            await service.pause()
        assert exc_info.value.status_code == 400


class TestResume:
    async def test_rejects_when_not_paused(self, service):
        service._settings.get_value.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.resume()
        assert exc_info.value.status_code == 400

    async def test_restores_tasks_and_clears_setting(self, service):
        paused_at = datetime.now(timezone.utc) - timedelta(days=3)
        service._settings.get_value.return_value = paused_at.isoformat()
        service._task_service.restore_after_pause.return_value = (4, 2)

        result = await service.resume()

        assert result.paused is False
        assert result.tasks_urgency_reset == 4
        assert result.tasks_deadline_shifted == 2

        service._task_service.restore_after_pause.assert_awaited_once()
        (delta,), _ = service._task_service.restore_after_pause.call_args
        assert delta > timedelta(days=2, hours=23)

        service._settings.set_value.assert_called_once_with(PAUSE_KEY, "")
