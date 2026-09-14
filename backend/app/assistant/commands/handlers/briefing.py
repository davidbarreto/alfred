import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.briefing.history_service import BriefingHistoryService

logger = logging.getLogger(__name__)


async def handle_briefing(command: str, arguments: dict[str, Any], service: BriefingHistoryService) -> Any:
    logger.debug("handle_briefing: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "history":
        results = await service.list(
            briefing_type=arguments.get("type"),
            limit=int(arguments.get("limit", 20)),
            offset=int(arguments.get("offset", 0)),
        )
        return [r.model_dump(mode="json") for r in results]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown briefing command: {command}")
