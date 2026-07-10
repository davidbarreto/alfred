import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.language.chunks.service import ChunkService
from app.features.language.production.schemas import ALL_TASK_TYPES, OPEN_ENDED_TASK_TYPES
from app.features.language.production.service import ProductionService
from app.features.language.tracks.schemas import TrackFilters
from app.features.language.tracks.service import TrackService

logger = logging.getLogger(__name__)

_WM_KEY = "language:pending"
_DEFAULT_ROUND_COUNT = 5


def _parse_count(arguments: dict[str, Any], default: int = _DEFAULT_ROUND_COUNT) -> int:
    raw = arguments.get("count")
    if raw is None:
        return default
    try:
        count = int(str(raw).strip())
    except ValueError:
        return default
    return count if count > 0 else default


async def handle_language(
    command: str,
    arguments: dict[str, Any],
    track_service: TrackService,
    chunk_service: ChunkService,
    working_memory_service: WorkingMemoryService,
    production_service: ProductionService | None = None,
) -> Any:
    logger.debug("handle_language: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "practice":
        return await _handle_practice(arguments, track_service, chunk_service, working_memory_service)
    if command == "review":
        return await _handle_review(arguments, track_service, chunk_service, working_memory_service)
    if command == "produce":
        if production_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Production practice service not available",
            )
        return await _handle_produce(arguments, track_service, production_service, working_memory_service)
    if command == "stop":
        return await _handle_stop(working_memory_service)

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
    count = _parse_count(arguments)

    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY,
        value=json.dumps({
            "mode": "practice",
            "chunk_id": chunk.id,
            "track_id": track.id,
            "track_code": track.code,
            "language_name": track.name,
            "text": chunk.text,
            "translation": chunk.translation,
            "remaining": count,
        }),
        importance=1.0,
    ))
    logger.info(
        "handle_language: practice started track=%s chunk_id=%d wm_id=%d rounds=%d",
        language_code, chunk.id, wm.id, count,
    )

    return {
        "mode": "practice",
        "wm_id": wm.id,
        "chunk_id": chunk.id,
        "track_id": track.id,
        "track_code": track.code,
        "language_name": track.name,
        "text": chunk.text,
        "translation": chunk.translation,
        "remaining": count,
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
    count = _parse_count(arguments)

    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY,
        value=json.dumps({
            "mode": "review",
            "chunk_id": chunk.id,
            "track_id": track.id,
            "track_code": track.code,
            "language_name": track.name,
            "text": chunk.text,
            "translation": chunk.translation,
            "remaining": count,
        }),
        importance=1.0,
    ))
    logger.info(
        "handle_language: review started track=%s chunk_id=%d wm_id=%d rounds=%d",
        language_code, chunk.id, wm.id, count,
    )

    return {
        "mode": "review",
        "wm_id": wm.id,
        "chunk_id": chunk.id,
        "track_id": track.id,
        "track_code": track.code,
        "language_name": track.name,
        "text": chunk.text,
        "translation": chunk.translation,
        "remaining": count,
    }


def _parse_produce_task_type(arguments: dict[str, Any]) -> str | None:
    """Return a valid task type or None. A numeric value is really the count ('/produce pt 3')."""
    raw = arguments.get("task_type")
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value.isdigit():
        arguments.setdefault("count", value)
        return None
    if value not in ALL_TASK_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown production task type: {value!r}. Use one of: {', '.join(ALL_TASK_TYPES)}",
        )
    return value


async def _handle_produce(
    arguments: dict[str, Any],
    track_service: TrackService,
    production_service: ProductionService,
    working_memory_service: WorkingMemoryService,
) -> dict[str, Any]:
    language_code = str(arguments.get("language_code", "")).strip().lower()
    if not language_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Language code is required")

    task_type = _parse_produce_task_type(arguments)
    # Open-ended tasks (journal, timed) are one whole text each; default to a single round.
    default_count = 1 if task_type in OPEN_ENDED_TASK_TYPES else _DEFAULT_ROUND_COUNT
    count = _parse_count(arguments, default=default_count)

    tracks = await track_service.get_tracks(TrackFilters(code=language_code, active_only=True))
    if not tracks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active track found for language: {language_code!r}",
        )
    track = tracks[0]

    task = await production_service.get_next_task(track.id, task_type)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No chunks due for production practice in track: {language_code!r}",
        )

    await _clear_pending(working_memory_service)

    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY,
        value=json.dumps({
            "mode": "produce",
            "chunk_id": task.chunk_id,
            "track_id": task.track_id,
            "track_code": task.track_code,
            "language_name": task.language_name,
            "text": task.text,
            "translation": task.translation,
            "task_type": task.task_type,
            "prompt_text": task.prompt_text,
            "time_limit_seconds": task.time_limit_seconds,
            "remaining": count,
        }),
        importance=1.0,
    ))
    logger.info(
        "handle_language: production started track=%s chunk_id=%s task=%s wm_id=%d rounds=%d",
        language_code, task.chunk_id, task.task_type, wm.id, count,
    )

    return {
        "mode": "produce",
        "wm_id": wm.id,
        "chunk_id": task.chunk_id,
        "track_id": task.track_id,
        "track_code": task.track_code,
        "language_name": task.language_name,
        "text": task.text,
        "translation": task.translation,
        "task_type": task.task_type,
        "prompt_text": task.prompt_text,
        "time_limit_seconds": task.time_limit_seconds,
        "remaining": count,
    }


async def _handle_stop(working_memory_service: WorkingMemoryService) -> dict[str, Any]:
    await _clear_pending(working_memory_service)
    logger.info("handle_language: practice/review session stopped")
    return {"mode": "stopped"}
