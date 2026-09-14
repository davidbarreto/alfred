import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.working_memory.schemas import WorkingMemoryFilters
from app.features.core.working_memory.service import WorkingMemoryService

logger = logging.getLogger(__name__)


async def handle_working_memory(command: str, arguments: dict[str, Any], service: WorkingMemoryService) -> Any:
    logger.debug("handle_working_memory: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        filters = WorkingMemoryFilters(
            key_contains=arguments.get("query"),
            expired=arguments.get("expired", "active"),
            limit=int(arguments.get("limit", 100)),
        )
        results = await service.list(filters)
        return [r.model_dump(mode="json") for r in results]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown working_memory command: {command}")
