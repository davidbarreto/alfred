import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.interviews.processes.schemas import InterviewProcessFilters
from app.features.organizer.interviews.processes.service import InterviewProcessService

logger = logging.getLogger(__name__)


async def handle_interview(command: str, arguments: dict[str, Any], service: InterviewProcessService) -> Any:
    logger.debug("handle_interview: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        filters = InterviewProcessFilters(
            limit=int(arguments.get("limit", 50)),
            company_id=int(arguments["company_id"]) if arguments.get("company_id") else None,
            status=arguments.get("status"),
        )
        results = await service.get_processes(filters)
        return [r.model_dump(mode="json") for r in results]

    if command == "get":
        process_id = int(arguments["id"])
        result = await service.get_process(process_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Interview process {process_id} not found")
        return result.model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown interview command: {command}")
