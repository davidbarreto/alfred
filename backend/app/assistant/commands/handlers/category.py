import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.finance.categories.service import CategoryService

logger = logging.getLogger(__name__)


async def handle_category(command: str, arguments: dict[str, Any], service: CategoryService) -> Any:
    logger.debug("handle_category: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        results = await service.list()
        return [r.model_dump(mode="json") for r in results]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown category command: {command}")
