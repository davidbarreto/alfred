import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.embeddings.schemas import EmbeddingSearchRequest
from app.features.core.embeddings.service import EmbeddingService

logger = logging.getLogger(__name__)

_RECALL_THRESHOLD = 0.5
_RECALL_LIMIT = 8


async def handle_recall(
    command: str,
    arguments: dict[str, Any],
    embedding_service: EmbeddingService,
) -> Any:
    logger.debug("handle_recall: command=%s args_keys=%s", command, list(arguments.keys()))

    if command != "search":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown recall command: {command}")

    query = str(arguments.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recall requires a query")

    results = await embedding_service.search(
        EmbeddingSearchRequest(
            query=query,
            source_types=["memory", "note", "task"],
            limit=_RECALL_LIMIT,
            threshold=_RECALL_THRESHOLD,
        )
    )
    logger.debug("handle_recall: query=%r results=%d", query, len(results))

    return [
        {
            "type": r.source_type,
            "source_id": r.source_id,
            "content": r.content,
            "similarity": r.similarity,
        }
        for r in results
    ]
