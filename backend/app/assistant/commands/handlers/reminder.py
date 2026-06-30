import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import parse_dt
from app.features.organizer.tasks.schemas import TaskCreate
from app.features.organizer.tasks.service import TaskService

logger = logging.getLogger(__name__)


async def handle_reminder(command: str, arguments: dict[str, Any], task_service: TaskService) -> Any:
    logger.debug("handle_reminder: command=%s args_keys=%s", command, list(arguments.keys()))

    if command != "set":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown reminder command: {command}")

    title = str(arguments.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reminder requires a title")

    remind_at = (
        parse_dt(arguments.get("remind_at"))
        or parse_dt(arguments.get("deadline"))
        or (datetime.now(timezone.utc) + timedelta(hours=1))
    )

    payload = TaskCreate(
        title=title,
        priority="HIGH",
        deadline=remind_at,
        tags=["reminder"],
        recurrence_rule=None,
    )
    result = await task_service.create_task(payload)
    logger.info("Reminder created: id=%d title=%r remind_at=%s", result.id, result.title, remind_at.isoformat())
    return {**result.model_dump(), "remind_at": remind_at.isoformat()}
