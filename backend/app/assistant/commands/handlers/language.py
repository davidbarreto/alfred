import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.language.chunks.service import ChunkService
from app.features.language.tracks.schemas import TrackFilters
from app.features.language.tracks.service import TrackService

logger = logging.getLogger(__name__)

_WM_KEY = "language:pending"


async def handle_language(
    command: str,
    arguments: dict[str, Any],
    track_service: TrackService,
    chunk_service: ChunkService,
    working_memory_service: WorkingMemoryService,
) -> Any:
    logger.debug("handle_language: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "practice":
        return await _handle_practice(arguments, track_service, chunk_service, working_memory_service)
    if command == "review":
        return await _handle_review(arguments, track_service, chunk_service, working_memory_service)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown language command: {command}")


async def _resolve_track_and_chunk(
    language_code: str,
    track_service: TrackService,
    chunk_service: ChunkService,
) -> tuple:
    tracks = await track_service.get_tracks(TrackFilters(code=language_code, active_only=True))
    if not tracks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active track found for language: {language_code!r}",
        )
    track = tracks[0]

    batches = await chunk_service.get_daily_batch(track.id)
    if not batches or not batches[0].chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No chunks due for practice in track: {language_code!r}",
        )
    chunk = batches[0].chunks[0]
    return track, chunk


async def _clear_pending(working_memory_service: WorkingMemoryService) -> None:
    existing = await working_memory_service.list(WorkingMemoryFilters(key=_WM_KEY, active_only=True))
    for item in existing:
        await working_memory_service.delete(item.id)
        logger.debug("handle_language: cleared stale pending WM id=%d", item.id)


async def _handle_practice(
    arguments: dict[str, Any],
    track_service: TrackService,
    chunk_service: ChunkService,
    working_memory_service: WorkingMemoryService,
) -> dict[str, Any]:
    language_code = str(arguments.get("language_code", "")).strip().lower()
    if not language_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Language code is required")

    track, chunk = await _resolve_track_and_chunk(language_code, track_service, chunk_service)
    await _clear_pending(working_memory_service)

    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY,
        value=json.dumps({
            "mode": "practice",
            "chunk_id": chunk.id,
            "track_id": track.id,
            "language_name": track.name,
            "text": chunk.text,
            "translation": chunk.translation,
        }),
        importance=1.0,
    ))
    logger.info(
        "handle_language: practice started track=%s chunk_id=%d wm_id=%d",
        language_code, chunk.id, wm.id,
    )

    return {
        "mode": "practice",
        "wm_id": wm.id,
        "chunk_id": chunk.id,
        "track_id": track.id,
        "language_name": track.name,
        "text": chunk.text,
        "translation": chunk.translation,
    }


async def _handle_review(
    arguments: dict[str, Any],
    track_service: TrackService,
    chunk_service: ChunkService,
    working_memory_service: WorkingMemoryService,
) -> dict[str, Any]:
    language_code = str(arguments.get("language_code", "")).strip().lower()
    if not language_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Language code is required")

    track, chunk = await _resolve_track_and_chunk(language_code, track_service, chunk_service)
    await _clear_pending(working_memory_service)

    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY,
        value=json.dumps({
            "mode": "review",
            "chunk_id": chunk.id,
            "track_id": track.id,
            "language_name": track.name,
            "text": chunk.text,
            "translation": chunk.translation,
        }),
        importance=1.0,
    ))
    logger.info(
        "handle_language: review started track=%s chunk_id=%d wm_id=%d",
        language_code, chunk.id, wm.id,
    )

    return {
        "mode": "review",
        "wm_id": wm.id,
        "chunk_id": chunk.id,
        "track_id": track.id,
        "language_name": track.name,
        "text": chunk.text,
        "translation": chunk.translation,
    }
