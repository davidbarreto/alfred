import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.pause.service import GlobalPauseService

logger = logging.getLogger(__name__)


async def handle_pause(command: str, arguments: dict[str, Any], pause_service: GlobalPauseService) -> Any:
    logger.debug("handle_pause: command=%s", command)

    if command == "start":
        result = await pause_service.pause()
        return result.model_dump(mode="json")

    if command == "stop":
        result = await pause_service.resume()
        return result.model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown pause command: {command}")
