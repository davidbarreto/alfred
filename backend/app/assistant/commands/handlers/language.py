import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.language.chunks.service import ChunkService
from app.features.language.conversation.service import ConversationService
from app.features.language.level_guidance import CEFR_LEVELS
from app.features.language.production.schemas import ALL_TASK_TYPES, CHUNKLESS_TASK_TYPES
from app.features.language.production.service import ProductionService
from app.features.language.sessions.service import format_feedback_summary
from app.features.language.tracks.schemas import TrackFilters
from app.features.language.tracks.service import TrackService

logger = logging.getLogger(__name__)

_WM_KEY = "language:pending"
_DEFAULT_ROUND_COUNT = 5
_DEFAULT_LANGUAGE_CODE = "en"
# Practice-chat modes — threaded, turn-by-turn, with end-of-session feedback.
_CHAT_MODES = {"roleplay", "conversation"}


def _resolve_language_code(arguments: dict[str, Any]) -> str:
    """Return the requested language code, defaulting to English when omitted."""
    return str(arguments.get("language_code", "")).strip().lower() or _DEFAULT_LANGUAGE_CODE


def _parse_count(arguments: dict[str, Any], default: int = _DEFAULT_ROUND_COUNT) -> int:
    raw = arguments.get("count")
    if raw is None:
        return default
    try:
        count = int(str(raw).strip())
    except ValueError:
        return default
    return count if count > 0 else default


def _parse_count_or_words(arguments: dict[str, Any], default: int = _DEFAULT_ROUND_COUNT) -> tuple[int, list[str] | None]:
    """Like `_parse_count`, but non-numeric input is treated as a comma-separated list of
    words/phrases to force-practice instead of being silently discarded, e.g.
    '/review pt cão, gato' -> (default, ["cão", "gato"])."""
    raw = arguments.get("count")
    if raw is None:
        return default, None
    text = str(raw).strip()
    if not text:
        return default, None
    try:
        count = int(text)
    except ValueError:
        words = [w.strip() for w in text.split(",") if w.strip()]
        return default, (words or None)
    return (count if count > 0 else default), None


def _resolve_level(arguments: dict[str, Any]) -> str | None:
    """Return the requested CEFR level override (e.g. 'level:a0'), or None if absent/invalid."""
    raw = arguments.get("level")
    if raw is None:
        return None
    level = str(raw).strip().upper()
    if level not in CEFR_LEVELS:
        logger.debug("handle_language: ignoring invalid level override %r", raw)
        return None
    return level


async def handle_language(
    command: str,
    arguments: dict[str, Any],
    track_service: TrackService,
    chunk_service: ChunkService,
    working_memory_service: WorkingMemoryService,
    production_service: ProductionService | None = None,
    conversation_service: ConversationService | None = None,
    message_id: int | None = None,
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
    if command == "conversation":
        if conversation_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Conversation practice service not available",
            )
        return await _handle_start_conversation(
            arguments, track_service, conversation_service, working_memory_service, message_id
        )
    if command == "stop":
        return await _handle_stop(working_memory_service, conversation_service)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown language command: {command}")


def _parse_conversation_args(rest: str, forced_mode: str | None) -> tuple[str, str, bool]:
    """Parse the free-text tail of /conversation into (mode, scenario_or_topic, voice_reply).

    A leading 'roleplay' token switches to roleplay mode (remaining text = scenario) unless
    forced_mode already says so (set via the /roleplay alias's implicit_flags). Free
    conversation defaults to spoken replies on ('text' opts out); roleplay defaults to
    spoken replies off ('voice' opts in) — matching how each mode is meant to be used."""
    tokens = rest.split()
    mode = forced_mode or "conversation"
    if mode != "roleplay" and tokens and tokens[0].lower() == "roleplay":
        mode = "roleplay"
        tokens = tokens[1:]

    voice_reply = mode == "conversation"
    filtered: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if mode == "conversation" and lowered == "text":
            voice_reply = False
            continue
        if mode == "roleplay" and lowered == "voice":
            voice_reply = True
            continue
        filtered.append(token)

    return mode, " ".join(filtered), voice_reply


async def _handle_start_conversation(
    arguments: dict[str, Any],
    track_service: TrackService,
    conversation_service: ConversationService,
    working_memory_service: WorkingMemoryService,
    message_id: int | None,
) -> dict[str, Any]:
    language_code = _resolve_language_code(arguments)
    if message_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="message_id is required to start a conversation"
        )

    rest = str(arguments.get("rest", "")).strip()
    mode, scenario_or_topic, voice_reply = _parse_conversation_args(rest, arguments.get("mode"))

    tracks = await track_service.get_tracks(TrackFilters(code=language_code, active_only=True))
    if not tracks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active track found for language: {language_code!r}",
        )
    track = tracks[0]

    if mode == "roleplay" and not scenario_or_topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A scenario is required for roleplay, e.g. /roleplay pt ordering coffee",
        )

    await _clear_pending(working_memory_service)

    level_override = _resolve_level(arguments)
    # Both modes run as a tracked thread, so turns and end-of-session feedback work the
    # same either way.
    start = await conversation_service.start(
        track.id, message_id, mode, scenario_or_topic or None, voice_reply,
        level_override=level_override,
    )
    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY,
        value=json.dumps({
            "mode": mode,
            "track_id": track.id,
            "track_code": track.code,
            "language_name": track.name,
            "thread_id": start.thread_id,
            "voice_reply": voice_reply,
        }),
        importance=1.0,
    ))
    logger.info(
        "handle_language: %s started track=%s thread_id=%d wm_id=%d topic=%r",
        mode, language_code, start.thread_id, wm.id, scenario_or_topic,
    )
    result = {
        "mode": mode,
        "wm_id": wm.id,
        "thread_id": start.thread_id,
        "track_id": track.id,
        "track_code": track.code,
        "language_name": track.name,
    }
    if mode == "roleplay":
        result["scenario"] = scenario_or_topic
    else:
        result["topic"] = scenario_or_topic or None
    # Roleplay always has an opening line; free conversation only does at A0.
    if start.opening_text is not None:
        result["opening_text"] = start.opening_text
        result["opening_audio_base64"] = start.opening_audio_base64
    return result


async def _resolve_track(language_code: str, track_service: TrackService):
    tracks = await track_service.get_tracks(TrackFilters(code=language_code, active_only=True))
    if not tracks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active track found for language: {language_code!r}",
        )
    return tracks[0]


async def _resolve_track_and_chunk(
    language_code: str,
    track_service: TrackService,
    chunk_service: ChunkService,
) -> tuple:
    track = await _resolve_track(language_code, track_service)

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


async def _forced_practice_wm_payload(
    mode: str,
    arguments: dict[str, Any],
    words: list[str],
    track,
    chunk_service: ChunkService,
) -> dict[str, Any]:
    """Force-create/resolve the requested chunks and shape them into a wm payload: the
    first chunk seeds the usual chunk_id/text/translation fields, the rest go into
    'forced_queue' for `advance_loop` to pop from instead of the daily due-batch."""
    level_override = _resolve_level(arguments)
    chunks = await chunk_service.force_practice_chunks(track.id, words, level_override=level_override)
    first, rest = chunks[0], chunks[1:]
    payload: dict[str, Any] = {
        "mode": mode,
        "chunk_id": first.id,
        "track_id": track.id,
        "track_code": track.code,
        "language_name": track.name,
        "text": first.text,
        "translation": first.translation,
        "remaining": len(chunks),
        "forced_queue": [{"chunk_id": c.id, "text": c.text, "translation": c.translation} for c in rest],
    }
    if mode == "practice":
        payload["feedback_history"] = []
    return payload


async def _handle_practice(
    arguments: dict[str, Any],
    track_service: TrackService,
    chunk_service: ChunkService,
    working_memory_service: WorkingMemoryService,
) -> dict[str, Any]:
    language_code = _resolve_language_code(arguments)
    count, words = _parse_count_or_words(arguments)

    if words:
        track = await _resolve_track(language_code, track_service)
        await _clear_pending(working_memory_service)
        wm_data = await _forced_practice_wm_payload("practice", arguments, words, track, chunk_service)
    else:
        track, chunk = await _resolve_track_and_chunk(language_code, track_service, chunk_service)
        await _clear_pending(working_memory_service)
        wm_data = {
            "mode": "practice",
            "chunk_id": chunk.id,
            "track_id": track.id,
            "track_code": track.code,
            "language_name": track.name,
            "text": chunk.text,
            "translation": chunk.translation,
            "remaining": count,
            "feedback_history": [],
        }

    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY, value=json.dumps(wm_data), importance=1.0,
    ))
    logger.info(
        "handle_language: practice started track=%s chunk_id=%d wm_id=%d rounds=%d forced=%s",
        language_code, wm_data["chunk_id"], wm.id, wm_data["remaining"], bool(words),
    )

    return {
        "mode": "practice",
        "wm_id": wm.id,
        "chunk_id": wm_data["chunk_id"],
        "track_id": wm_data["track_id"],
        "track_code": wm_data["track_code"],
        "language_name": wm_data["language_name"],
        "text": wm_data["text"],
        "translation": wm_data["translation"],
        "remaining": wm_data["remaining"],
    }


async def _handle_review(
    arguments: dict[str, Any],
    track_service: TrackService,
    chunk_service: ChunkService,
    working_memory_service: WorkingMemoryService,
) -> dict[str, Any]:
    language_code = _resolve_language_code(arguments)
    count, words = _parse_count_or_words(arguments)

    if words:
        track = await _resolve_track(language_code, track_service)
        await _clear_pending(working_memory_service)
        wm_data = await _forced_practice_wm_payload("review", arguments, words, track, chunk_service)
    else:
        track, chunk = await _resolve_track_and_chunk(language_code, track_service, chunk_service)
        await _clear_pending(working_memory_service)
        wm_data = {
            "mode": "review",
            "chunk_id": chunk.id,
            "track_id": track.id,
            "track_code": track.code,
            "language_name": track.name,
            "text": chunk.text,
            "translation": chunk.translation,
            "remaining": count,
        }

    wm = await working_memory_service.create(WorkingMemoryCreate(
        key=_WM_KEY, value=json.dumps(wm_data), importance=1.0,
    ))
    logger.info(
        "handle_language: review started track=%s chunk_id=%d wm_id=%d rounds=%d forced=%s",
        language_code, wm_data["chunk_id"], wm.id, wm_data["remaining"], bool(words),
    )

    return {
        "mode": "review",
        "wm_id": wm.id,
        "chunk_id": wm_data["chunk_id"],
        "track_id": wm_data["track_id"],
        "track_code": wm_data["track_code"],
        "language_name": wm_data["language_name"],
        "text": wm_data["text"],
        "translation": wm_data["translation"],
        "remaining": wm_data["remaining"],
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
    language_code = _resolve_language_code(arguments)

    task_type = _parse_produce_task_type(arguments)
    # Chunk-less tasks (journal, timed, speak, retell) are one whole response each;
    # default to a single round.
    default_count = 1 if task_type in CHUNKLESS_TASK_TYPES else _DEFAULT_ROUND_COUNT
    count = _parse_count(arguments, default=default_count)

    tracks = await track_service.get_tracks(TrackFilters(code=language_code, active_only=True))
    if not tracks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active track found for language: {language_code!r}",
        )
    track = tracks[0]

    level_override = _resolve_level(arguments)
    task = await production_service.get_next_task(track.id, task_type, level_override=level_override)
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


async def _handle_stop(
    working_memory_service: WorkingMemoryService,
    conversation_service: ConversationService | None = None,
) -> dict[str, Any]:
    existing = await working_memory_service.list(WorkingMemoryFilters(key=_WM_KEY, active_only=True))
    result: dict[str, Any] = {"mode": "stopped"}
    for item in existing:
        try:
            data = json.loads(item.value)
        except (json.JSONDecodeError, TypeError):
            data = {}

        # Both practice-chat modes end the same way: close the thread and generate
        # end-of-session coaching feedback from its turns.
        mode = data.get("mode")
        if mode in _CHAT_MODES and conversation_service is not None and data.get("thread_id") is not None:
            end = await conversation_service.end(data["thread_id"])
            result = {"mode": "stopped", "tip": end.tip, "turn_count": end.turn_count}
        elif mode == "practice" and data.get("feedback_history"):
            result = {"mode": "stopped", "summary": format_feedback_summary(data["feedback_history"])}

        await working_memory_service.delete(item.id)
        logger.debug("handle_language: cleared stale pending WM id=%d", item.id)

    logger.info("handle_language: practice/review/conversation session stopped")
    return result
