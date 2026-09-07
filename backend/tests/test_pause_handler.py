from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.pause import handle_pause
from app.features.core.pause.schemas import PauseResumeRead, PauseStateRead


@pytest.fixture
def mock_service():
    return AsyncMock()


class TestHandlePauseStart:
    async def test_pauses_and_returns_state(self, mock_service):
        mock_service.pause.return_value = PauseStateRead(
            paused=True, paused_at=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        )

        result = await handle_pause("start", {}, mock_service)

        assert result["paused"] is True
        mock_service.pause.assert_awaited_once()


class TestHandlePauseStop:
    async def test_resumes_and_returns_summary(self, mock_service):
        mock_service.resume.return_value = PauseResumeRead(
            resumed_at=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
            tasks_urgency_reset=3,
            tasks_deadline_shifted=1,
        )

        result = await handle_pause("stop", {}, mock_service)

        assert result["tasks_urgency_reset"] == 3
        assert result["tasks_deadline_shifted"] == 1
        mock_service.resume.assert_awaited_once()


class TestHandlePauseUnknownCommand:
    async def test_raises_400(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_pause("bogus", {}, mock_service)
        assert exc_info.value.status_code == 400
