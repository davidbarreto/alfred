import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.features.core.working_memory.schemas import WorkingMemoryCreate
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.cs.stats.service import StatsService, format_context_summary

logger = logging.getLogger(__name__)

_WM_KEY = "cs:context"
_CONTEXT_TTL = timedelta(hours=4)


async def handle_cs(
    command: str,
    arguments: dict[str, Any],
    stats_service: StatsService,
    working_memory_service: WorkingMemoryService,
) -> Any:
    logger.debug("handle_cs: command=%s args_keys=%s", command, list(arguments.keys()))

    if command != "context":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown cs command: {command}")

    summary = await stats_service.get_summary()
    value = format_context_summary(summary)
    expires_at = datetime.now(timezone.utc) + _CONTEXT_TTL

    wm = await working_memory_service.upsert(WorkingMemoryCreate(
        key=_WM_KEY, value=value, importance=0.7, expires_at=expires_at,
    ))
    logger.info("handle_cs: context loaded wm_id=%d expires_at=%s", wm.id, expires_at.isoformat())

    return {
        "wm_id": wm.id,
        "summary": value,
        "expires_at": expires_at.isoformat(),
    }
