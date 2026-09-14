import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.watcher.repository import get_alerts, get_watcher, get_watchers
from app.features.watcher.schemas import AlertRead, WatcherRead

logger = logging.getLogger(__name__)


async def handle_watcher(command: str, arguments: dict[str, Any], session: AsyncSession) -> Any:
    logger.debug("handle_watcher: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        limit = int(arguments.get("limit", 100))
        watchers = await get_watchers(session=session, limit=limit)
        return [WatcherRead.model_validate(w).model_dump(mode="json") for w in watchers]

    if command == "get":
        watcher_id = int(arguments["id"])
        watcher = await get_watcher(session=session, watcher_id=watcher_id)
        if watcher is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Watcher {watcher_id} not found")
        return WatcherRead.model_validate(watcher).model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown watcher command: {command}")


async def handle_alert(command: str, arguments: dict[str, Any], session: AsyncSession) -> Any:
    logger.debug("handle_alert: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        alerts = await get_alerts(
            session=session,
            status=arguments.get("status"),
            config_id=int(arguments["config_id"]) if arguments.get("config_id") else None,
            limit=int(arguments.get("limit", 20)),
        )
        return [AlertRead.model_validate(a).model_dump(mode="json") for a in alerts]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown alert command: {command}")
