import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.pause.repository import PauseLogRepository
from app.features.core.pause.schemas import PauseLogRead, PauseResumeRead, PauseStateRead
from app.features.core.settings.service import SettingService
from app.features.organizer.tasks.service import TaskService

logger = logging.getLogger(__name__)

PAUSE_KEY = "core.paused_at"


class GlobalPauseService:
    """A single global switch: while paused, reminders/briefing pushes are muted and
    task urgency stops escalating. Resuming restores urgency and shifts overdue
    deadlines forward by the pause duration, so lost time isn't held against you.
    """

    def __init__(self, session: AsyncSession, task_service: TaskService) -> None:
        self._settings = SettingService(session)
        self._task_service = task_service
        self._pause_log_repo = PauseLogRepository(session)

    async def get_state(self) -> PauseStateRead:
        raw = await self._settings.get_value(PAUSE_KEY)
        paused_at = datetime.fromisoformat(raw) if raw else None
        return PauseStateRead(paused=paused_at is not None, paused_at=paused_at)

    async def is_paused(self) -> bool:
        state = await self.get_state()
        return state.paused

    async def pause(self) -> PauseStateRead:
        state = await self.get_state()
        if state.paused:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already paused")
        now = datetime.now(timezone.utc)
        await self._settings.set_value(PAUSE_KEY, now.isoformat())
        logger.info("Global pause enabled: paused_at=%s", now.isoformat())
        return PauseStateRead(paused=True, paused_at=now)

    async def resume(self) -> PauseResumeRead:
        state = await self.get_state()
        if not state.paused:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not paused")
        now = datetime.now(timezone.utc)
        delta = now - state.paused_at
        urgency_reset, deadlines_shifted = await self._task_service.restore_after_pause(delta)
        await self._settings.set_value(PAUSE_KEY, "")
        await self._pause_log_repo.create(
            started_at=state.paused_at,
            ended_at=now,
            tasks_urgency_reset=urgency_reset,
            tasks_deadline_shifted=deadlines_shifted,
        )
        logger.info(
            "Global pause disabled: paused_at=%s resumed_at=%s urgency_reset=%d deadlines_shifted=%d",
            state.paused_at.isoformat(), now.isoformat(), urgency_reset, deadlines_shifted,
        )
        return PauseResumeRead(
            resumed_at=now,
            tasks_urgency_reset=urgency_reset,
            tasks_deadline_shifted=deadlines_shifted,
        )

    async def list_history(self, limit: int = 100) -> list[PauseLogRead]:
        logs = await self._pause_log_repo.list(limit=limit)
        return [PauseLogRead.model_validate(log) for log in logs]
