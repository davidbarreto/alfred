import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.language.grammar_scope.schemas import GrammarScopeFilters
from app.features.language.grammar_scope.service import GrammarScopeService

logger = logging.getLogger(__name__)


async def handle_grammar_scope(command: str, arguments: dict[str, Any], service: GrammarScopeService) -> Any:
    logger.debug("handle_grammar_scope: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        if not arguments.get("track_id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="grammar_scope.list requires track_id",
            )
        filters = GrammarScopeFilters(
            track_id=int(arguments["track_id"]),
            status=arguments.get("status", "ALL"),
        )
        results = await service.get_scopes(filters)
        return [r.model_dump(mode="json") for r in results]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown grammar_scope command: {command}")
