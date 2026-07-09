import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.assistant.commands.handlers.language import handle_language
from app.features.core.working_memory.schemas import WorkingMemoryRead
from app.features.language.chunks.schemas import ChunkRead, DailyBatchRead
from app.features.language.tracks.schemas import TrackRead


def _make_track(**kwargs) -> TrackRead:
    return TrackRead(
        id=kwargs.get("id", 3),
        code=kwargs.get("code", "en"),
        name=kwargs.get("name", "English"),
        level=kwargs.get("level", "B1"),
        daily_quota=kwargs.get("daily_quota", 10),
        review_mode=kwargs.get("review_mode", "balanced"),
        active=kwargs.get("active", True),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_chunk(**kwargs) -> ChunkRead:
    return ChunkRead(
        id=kwargs.get("id", 42),
        track_id=kwargs.get("track_id", 3),
        grammar_scope_id=None,
        chunk_type=kwargs.get("chunk_type", "word"),
        text=kwargs.get("text", "The rain fell all night long"),
        translation=kwargs.get("translation", "A chuva caiu durante a noite toda"),
        example_sentence=None,
        example_translation=None,
        cefr_level="B1",
        frequency_rank=None,
        frequency_source=None,
        stability=0.0,
        difficulty=5.0,
        due_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_review_at=None,
        repetitions=0,
        lapses=0,
        consecutive_failures=0,
        state="new",
        status="active",
        is_leech=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_wm_read(id: int = 7, chunk_id: int = 42, track_id: int = 3, mode: str = "practice") -> WorkingMemoryRead:
    return WorkingMemoryRead(
        id=id,
        key="language:pending",
        value=json.dumps({"mode": mode, "chunk_id": chunk_id, "track_id": track_id}),
        importance=1.0,
        expires_at=None,
        session_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_services(tracks=None, batches=None, existing_wm=None, created_wm=None):
    track_service = AsyncMock()
    track_service.get_tracks = AsyncMock(return_value=tracks if tracks is not None else [_make_track()])

    chunk_service = AsyncMock()
    chunk = _make_chunk()
    batch = DailyBatchRead(track_id=3, track_code="en", chunks=[chunk], total_due=5)
    chunk_service.get_daily_batch = AsyncMock(return_value=batches if batches is not None else [batch])

    wm_service = AsyncMock()
    wm_service.list = AsyncMock(return_value=existing_wm if existing_wm is not None else [])
    wm_service.delete = AsyncMock(return_value=True)
    wm_service.create = AsyncMock(return_value=created_wm if created_wm is not None else _make_wm_read())

    return track_service, chunk_service, wm_service


class TestHandleLanguagePractice:
    async def test_returns_chunk_and_wm_ids(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        result = await handle_language("practice", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        assert result["chunk_id"] == 42
        assert result["track_id"] == 3
        assert result["track_code"] == "en"
        assert result["wm_id"] == 7
        assert result["language_name"] == "English"
        assert result["text"] == "The rain fell all night long"
        assert result["translation"] == "A chuva caiu durante a noite toda"
        assert result["mode"] == "practice"
        assert result["remaining"] == 5

    async def test_creates_wm_with_correct_key_and_value(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        await handle_language("practice", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        wm_svc.create.assert_called_once()
        created = wm_svc.create.call_args[0][0]
        assert created.key == "language:pending"
        payload = json.loads(created.value)
        assert payload["mode"] == "practice"
        assert payload["chunk_id"] == 42
        assert payload["track_id"] == 3
        assert payload["track_code"] == "en"
        assert payload["language_name"] == "English"
        assert payload["text"] == "The rain fell all night long"
        assert payload["translation"] == "A chuva caiu durante a noite toda"
        assert payload["remaining"] == 5

    async def test_default_round_count_when_not_specified(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        result = await handle_language("practice", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        assert result["remaining"] == 5

    async def test_uses_explicit_round_count(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        result = await handle_language(
            "practice", {"language_code": "en", "count": "3"}, track_svc, chunk_svc, wm_svc
        )
        assert result["remaining"] == 3

    async def test_falls_back_to_default_on_invalid_count(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        result = await handle_language(
            "practice", {"language_code": "en", "count": "not-a-number"}, track_svc, chunk_svc, wm_svc
        )
        assert result["remaining"] == 5

    async def test_clears_existing_pending_wm_before_creating_new(self):
        old_wm = _make_wm_read(id=5, chunk_id=10)
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[old_wm])
        await handle_language("practice", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        wm_svc.delete.assert_called_once_with(5)
        wm_svc.create.assert_called_once()

    async def test_filters_track_by_language_code(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        await handle_language("practice", {"language_code": "EN"}, track_svc, chunk_svc, wm_svc)
        filters = track_svc.get_tracks.call_args[0][0]
        assert filters.code == "en"
        assert filters.active_only is True

    async def test_raises_404_when_track_not_found(self):
        track_svc, chunk_svc, wm_svc = _make_services(tracks=[])
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("practice", {"language_code": "xx"}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 404

    async def test_raises_404_when_no_due_chunks(self):
        empty_batch = DailyBatchRead(track_id=3, track_code="en", chunks=[], total_due=0)
        track_svc, chunk_svc, wm_svc = _make_services(batches=[empty_batch])
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("practice", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 404

    async def test_raises_404_when_daily_batch_empty(self):
        track_svc, chunk_svc, wm_svc = _make_services(batches=[])
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("practice", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 404

    async def test_raises_400_for_unknown_language_command(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("bogus", {}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 400

    async def test_raises_400_when_language_code_missing(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("practice", {}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 400


class TestHandleLanguageReview:
    async def test_returns_chunk_and_wm_ids(self):
        track_svc, chunk_svc, wm_svc = _make_services(created_wm=_make_wm_read(mode="review"))
        result = await handle_language("review", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        assert result["chunk_id"] == 42
        assert result["track_id"] == 3
        assert result["wm_id"] == 7
        assert result["language_name"] == "English"
        assert result["text"] == "The rain fell all night long"
        assert result["translation"] == "A chuva caiu durante a noite toda"
        assert result["mode"] == "review"

    async def test_creates_wm_with_correct_key_and_mode(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        await handle_language("review", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        wm_svc.create.assert_called_once()
        created = wm_svc.create.call_args[0][0]
        assert created.key == "language:pending"
        payload = json.loads(created.value)
        assert payload["mode"] == "review"
        assert payload["chunk_id"] == 42
        assert payload["track_id"] == 3

    async def test_clears_existing_pending_wm_before_creating_new(self):
        old_wm = _make_wm_read(id=5, chunk_id=10, mode="practice")
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[old_wm])
        await handle_language("review", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        wm_svc.delete.assert_called_once_with(5)
        wm_svc.create.assert_called_once()

    async def test_raises_404_when_track_not_found(self):
        track_svc, chunk_svc, wm_svc = _make_services(tracks=[])
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("review", {"language_code": "xx"}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 404

    async def test_raises_404_when_no_due_chunks(self):
        empty_batch = DailyBatchRead(track_id=3, track_code="en", chunks=[], total_due=0)
        track_svc, chunk_svc, wm_svc = _make_services(batches=[empty_batch])
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("review", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 404

    async def test_raises_400_when_language_code_missing(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("review", {}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 400


class TestHandleLanguageStop:
    async def test_stop_clears_pending_wm(self):
        existing = _make_wm_read(id=5, chunk_id=10)
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[existing])
        result = await handle_language("stop", {}, track_svc, chunk_svc, wm_svc)
        wm_svc.delete.assert_called_once_with(5)
        assert result["mode"] == "stopped"

    async def test_stop_is_noop_when_nothing_pending(self):
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[])
        result = await handle_language("stop", {}, track_svc, chunk_svc, wm_svc)
        wm_svc.delete.assert_not_called()
        assert result["mode"] == "stopped"


class TestLanguageCommandRegistry:
    async def test_detect_practice_command(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/practice en")
        assert len(commands) == 1
        assert commands[0].type == "language"
        assert commands[0].command == "practice"
        assert commands[0].args["language_code"] == "en"

    async def test_detect_practice_alias(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/pr pt")
        assert len(commands) == 1
        assert commands[0].command == "practice"
        assert commands[0].args["language_code"] == "pt"

    async def test_detect_review_command(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/review fr")
        assert len(commands) == 1
        assert commands[0].type == "language"
        assert commands[0].command == "review"
        assert commands[0].args["language_code"] == "fr"

    async def test_detect_review_alias(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/rv es")
        assert len(commands) == 1
        assert commands[0].command == "review"
        assert commands[0].args["language_code"] == "es"

    async def test_practice_requires_language_arg(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/practice")
        assert commands == []

    async def test_review_requires_language_arg(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/review")
        assert commands == []

    async def test_practice_parses_optional_count(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/practice pt 3")
        assert len(commands) == 1
        assert commands[0].args["language_code"] == "pt"
        assert commands[0].args["count"] == "3"

    async def test_practice_without_count_has_no_count_arg(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/practice pt")
        assert "count" not in commands[0].args

    async def test_review_parses_optional_count(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/review fr 10")
        assert len(commands) == 1
        assert commands[0].args["language_code"] == "fr"
        assert commands[0].args["count"] == "10"

    async def test_detect_stop_command(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/stop")
        assert len(commands) == 1
        assert commands[0].type == "language"
        assert commands[0].command == "stop"

    async def test_detect_stop_practice_alias(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/stop-practice")
        assert len(commands) == 1
        assert commands[0].command == "stop"

    async def test_detect_stop_review_alias(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/stop-review")
        assert len(commands) == 1
        assert commands[0].command == "stop"
