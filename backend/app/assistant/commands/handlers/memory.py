import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.memories.schemas import MemoryFilters
from app.features.core.memories.service import MemoryService

logger = logging.getLogger(__name__)


async def handle_memory(command: str, arguments: dict[str, Any], service: MemoryService) -> Any:
    logger.debug("handle_memory: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        filters = MemoryFilters(
            category=arguments.get("category"),
            active=arguments.get("active"),
            limit=int(arguments.get("limit", 100)),
        )
        results = await service.list(filters)
        return [r.model_dump(mode="json") for r in results]

    if command == "search":
        filters = MemoryFilters(
            q=arguments["query"],
            category=arguments.get("category"),
            limit=int(arguments.get("limit", 100)),
        )
        results = await service.list(filters)
        return [r.model_dump(mode="json") for r in results]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown memory command: {command}")
