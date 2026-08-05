import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.embeddings.schemas import EmbeddingSearchRequest
from app.features.core.embeddings.service import EmbeddingService

logger = logging.getLogger(__name__)

_RECALL_THRESHOLD = 0.5
_RECALL_LIMIT = 8

# "note_title" is a second, title-only embedding kept alongside the full
# "note" embedding (see app.features.organizer.notes.service) so short,
# title-shaped queries still score well against notes with a long body.
# It's collapsed back onto "note" below so a single note never appears twice.
_SOURCE_TYPES = ["memory", "note", "note_title", "task"]
_TITLE_TO_CANONICAL_TYPE = {"note_title": "note"}


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
            source_types=_SOURCE_TYPES,
            # Fetch extra headroom since a matching note can surface as two rows
            # (full note + title) that collapse into one result below.
            limit=_RECALL_LIMIT * 2,
            threshold=_RECALL_THRESHOLD,
            feature="recall",
        )
    )
    logger.debug("handle_recall: query=%r results=%d", query, len(results))

    return _dedupe_results(results)[:_RECALL_LIMIT]


def _dedupe_results(results: list) -> list[dict[str, Any]]:
    """Collapse the "note" and "note_title" hits for the same note into one entry.

    Keeps the best similarity score seen for the note (whichever embedding
    matched harder) but prefers the full-note content for display, since a
    title-only hit's content is just the title.
    """
    merged: dict[tuple[str, int], dict[str, Any]] = {}
    for r in sorted(results, key=lambda r: r.similarity, reverse=True):
        canonical_type = _TITLE_TO_CANONICAL_TYPE.get(r.source_type, r.source_type)
        key = (canonical_type, r.source_id)
        existing = merged.get(key)
        if existing is None:
            merged[key] = {
                "type": canonical_type,
                "source_id": r.source_id,
                "content": r.content,
                "similarity": r.similarity,
            }
        elif r.source_type != "note_title":
            existing["content"] = r.content
    return sorted(merged.values(), key=lambda item: item["similarity"], reverse=True)
