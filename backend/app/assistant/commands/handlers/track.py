import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.language.tracks.schemas import TrackFilters
from app.features.language.tracks.service import TrackService

logger = logging.getLogger(__name__)


async def handle_track(command: str, arguments: dict[str, Any], service: TrackService) -> Any:
    logger.debug("handle_track: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        filters = TrackFilters(
            active_only=arguments.get("active_only", True),
            exclude_paused=arguments.get("exclude_paused", False),
        )
        results = await service.get_tracks(filters)
        return [r.model_dump(mode="json") for r in results]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown track command: {command}")
