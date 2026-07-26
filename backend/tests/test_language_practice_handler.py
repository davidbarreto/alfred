import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.assistant.commands.handlers.language import (
    _parse_conversation_args,
    _parse_count_or_words,
    _resolve_level,
    handle_language,
)
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
        prod_stability=0.0,
        prod_difficulty=5.0,
        prod_due_at=None,
        prod_last_review_at=None,
        prod_repetitions=0,
        prod_lapses=0,
        prod_consecutive_failures=0,
        prod_state="new",
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
        assert payload["feedback_history"] == []

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

    async def test_non_numeric_count_is_treated_as_forced_words(self):
        # A non-numeric "count" (positional slot after language_code) is force-practice
        # word(s), not silently discarded — e.g. '/practice en some phrase'.
        track_svc, chunk_svc, wm_svc = _make_services()
        forced_chunk = _make_chunk(id=99, text="some phrase", translation="uma frase")
        chunk_svc.force_practice_chunks = AsyncMock(return_value=[forced_chunk])
        result = await handle_language(
            "practice", {"language_code": "en", "count": "some phrase"}, track_svc, chunk_svc, wm_svc
        )
        chunk_svc.force_practice_chunks.assert_awaited_once_with(3, ["some phrase"], level_override=None)
        assert result["chunk_id"] == 99
        assert result["remaining"] == 1

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

    async def test_defaults_to_english_when_language_code_missing(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        result = await handle_language("practice", {}, track_svc, chunk_svc, wm_svc)
        assert result["track_code"] == "en"
        filters = track_svc.get_tracks.call_args[0][0]
        assert filters.code == "en"


class TestForcedPractice:
    async def test_review_with_multiple_comma_separated_words(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        chunks = [
            _make_chunk(id=101, text="cão", translation="dog"),
            _make_chunk(id=102, text="gato", translation="cat"),
        ]
        chunk_svc.force_practice_chunks = AsyncMock(return_value=chunks)

        result = await handle_language(
            "review", {"language_code": "en", "count": "cão, gato"}, track_svc, chunk_svc, wm_svc
        )

        chunk_svc.force_practice_chunks.assert_awaited_once_with(3, ["cão", "gato"], level_override=None)
        assert result["mode"] == "review"
        assert result["chunk_id"] == 101
        assert result["remaining"] == 2

        wm_value = json.loads(wm_svc.create.call_args[0][0].value)
        assert wm_value["forced_queue"] == [{"chunk_id": 102, "text": "gato", "translation": "cat"}]

    async def test_review_with_words_and_level_override(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        chunk_svc.force_practice_chunks = AsyncMock(return_value=[_make_chunk(id=101, text="cão")])

        await handle_language(
            "review", {"language_code": "en", "count": "cão", "level": "a0"}, track_svc, chunk_svc, wm_svc
        )

        chunk_svc.force_practice_chunks.assert_awaited_once_with(3, ["cão"], level_override="A0")

    async def test_practice_forced_words_seeds_empty_feedback_history(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        chunk_svc.force_practice_chunks = AsyncMock(return_value=[_make_chunk(id=101, text="cão")])

        await handle_language(
            "practice", {"language_code": "en", "count": "cão"}, track_svc, chunk_svc, wm_svc
        )

        wm_value = json.loads(wm_svc.create.call_args[0][0].value)
        assert wm_value["feedback_history"] == []

    async def test_invalid_level_is_ignored(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        chunk_svc.force_practice_chunks = AsyncMock(return_value=[_make_chunk(id=101, text="cão")])

        await handle_language(
            "review", {"language_code": "en", "count": "cão", "level": "z9"}, track_svc, chunk_svc, wm_svc
        )

        chunk_svc.force_practice_chunks.assert_awaited_once_with(3, ["cão"], level_override=None)


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

    async def test_defaults_to_english_when_language_code_missing(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        result = await handle_language("review", {}, track_svc, chunk_svc, wm_svc)
        assert result["track_code"] == "en"
        filters = track_svc.get_tracks.call_args[0][0]
        assert filters.code == "en"


def _make_production_task(**kwargs):
    from app.features.language.production.schemas import ProductionTaskRead
    return ProductionTaskRead(
        track_id=kwargs.get("track_id", 3),
        track_code=kwargs.get("track_code", "en"),
        language_name=kwargs.get("language_name", "English"),
        chunk_id=kwargs.get("chunk_id", 42),
        task_type=kwargs.get("task_type", "sentence"),
        prompt_text=kwargs.get("prompt_text", 'Write an original sentence in English using "rain".'),
        text=kwargs.get("text", "rain"),
        translation=kwargs.get("translation", "chuva"),
        total_due=kwargs.get("total_due", 4),
        time_limit_seconds=kwargs.get("time_limit_seconds"),
    )


def _make_production_service(task=...):
    from unittest.mock import AsyncMock as _AsyncMock
    production_service = _AsyncMock()
    production_service.get_next_task = _AsyncMock(
        return_value=_make_production_task() if task is ... else task
    )
    return production_service


class TestHandleLanguageProduce:
    async def test_returns_task_and_wm_id(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service()
        result = await handle_language(
            "produce", {"language_code": "en"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        assert result["mode"] == "produce"
        assert result["wm_id"] == 7
        assert result["chunk_id"] == 42
        assert result["task_type"] == "sentence"
        assert "rain" in result["prompt_text"]
        assert result["remaining"] == 5

    async def test_creates_wm_with_produce_mode_and_task(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service()
        await handle_language(
            "produce", {"language_code": "en"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        created = wm_svc.create.call_args[0][0]
        assert created.key == "language:pending"
        payload = json.loads(created.value)
        assert payload["mode"] == "produce"
        assert payload["chunk_id"] == 42
        assert payload["task_type"] == "sentence"
        assert payload["prompt_text"].startswith("Write an original sentence")
        assert payload["remaining"] == 5

    async def test_passes_explicit_task_type(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service(_make_production_task(task_type="translate"))
        result = await handle_language(
            "produce", {"language_code": "en", "task_type": "translate"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        assert production_svc.get_next_task.call_args[0][1] == "translate"
        assert result["task_type"] == "translate"

    async def test_numeric_task_type_is_treated_as_count(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service()
        result = await handle_language(
            "produce", {"language_code": "en", "task_type": "3"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        assert production_svc.get_next_task.call_args[0][1] is None
        assert result["remaining"] == 3

    async def test_journal_defaults_to_one_round(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service(_make_production_task(
            task_type="journal", chunk_id=None, text=None, translation=None,
            prompt_text="Write a short journal entry in English about your day so far.",
            total_due=1,
        ))
        result = await handle_language(
            "produce", {"language_code": "en", "task_type": "journal"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        assert production_svc.get_next_task.call_args[0][1] == "journal"
        assert result["task_type"] == "journal"
        assert result["chunk_id"] is None
        assert result["remaining"] == 1

    async def test_speak_defaults_to_one_round(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service(_make_production_task(
            task_type="speak", chunk_id=None, text=None, translation=None,
            prompt_text="Speak for about a minute in English about your plans for the weekend.",
            total_due=1,
        ))
        result = await handle_language(
            "produce", {"language_code": "en", "task_type": "speak"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        assert production_svc.get_next_task.call_args[0][1] == "speak"
        assert result["task_type"] == "speak"
        assert result["chunk_id"] is None
        assert result["remaining"] == 1

    async def test_retell_prompt_carries_passage_into_wm(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        passage = "Yesterday Tom lost his keys. A neighbor found them."
        production_svc = _make_production_service(_make_production_task(
            task_type="retell", chunk_id=None, text=None, translation=None,
            prompt_text=f"Listen to this short passage, then retell it in English in your own words:\n\n{passage}",
            total_due=1,
        ))
        result = await handle_language(
            "produce", {"language_code": "en", "task_type": "retell"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        payload = json.loads(wm_svc.create.call_args[0][0].value)
        assert payload["task_type"] == "retell"
        assert passage in payload["prompt_text"]
        assert result["remaining"] == 1

    async def test_open_ended_explicit_count_overrides_default(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service(_make_production_task(task_type="journal", chunk_id=None))
        result = await handle_language(
            "produce", {"language_code": "en", "task_type": "journal", "count": "3"},
            track_svc, chunk_svc, wm_svc, production_service=production_svc,
        )
        assert result["remaining"] == 3

    async def test_timed_carries_time_limit_into_wm(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service(_make_production_task(
            task_type="timed", chunk_id=None, time_limit_seconds=300,
        ))
        result = await handle_language(
            "produce", {"language_code": "en", "task_type": "timed"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        payload = json.loads(wm_svc.create.call_args[0][0].value)
        assert payload["time_limit_seconds"] == 300
        assert payload["task_type"] == "timed"
        assert result["time_limit_seconds"] == 300

    async def test_raises_400_on_unknown_task_type(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service()
        with pytest.raises(HTTPException) as exc_info:
            await handle_language(
                "produce", {"language_code": "en", "task_type": "juggle"}, track_svc, chunk_svc, wm_svc,
                production_service=production_svc,
            )
        assert exc_info.value.status_code == 400

    async def test_raises_404_when_track_not_found(self):
        track_svc, chunk_svc, wm_svc = _make_services(tracks=[])
        production_svc = _make_production_service()
        with pytest.raises(HTTPException) as exc_info:
            await handle_language(
                "produce", {"language_code": "xx"}, track_svc, chunk_svc, wm_svc,
                production_service=production_svc,
            )
        assert exc_info.value.status_code == 404

    async def test_raises_404_when_nothing_due_for_production(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service(task=None)
        with pytest.raises(HTTPException) as exc_info:
            await handle_language(
                "produce", {"language_code": "en"}, track_svc, chunk_svc, wm_svc,
                production_service=production_svc,
            )
        assert exc_info.value.status_code == 404

    async def test_raises_503_without_production_service(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        with pytest.raises(HTTPException) as exc_info:
            await handle_language("produce", {"language_code": "en"}, track_svc, chunk_svc, wm_svc)
        assert exc_info.value.status_code == 503

    async def test_passes_level_override_to_get_next_task(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service()
        await handle_language(
            "produce", {"language_code": "en", "task_type": "retell", "level": "a0"},
            track_svc, chunk_svc, wm_svc, production_service=production_svc,
        )
        assert production_svc.get_next_task.call_args.kwargs["level_override"] == "A0"

    async def test_no_level_arg_passes_none(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service()
        await handle_language(
            "produce", {"language_code": "en"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        assert production_svc.get_next_task.call_args.kwargs["level_override"] is None

    async def test_clears_existing_pending_wm_before_creating_new(self):
        old_wm = _make_wm_read(id=5, chunk_id=10, mode="practice")
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[old_wm])
        production_svc = _make_production_service()
        await handle_language(
            "produce", {"language_code": "en"}, track_svc, chunk_svc, wm_svc,
            production_service=production_svc,
        )
        wm_svc.delete.assert_called_once_with(5)
        wm_svc.create.assert_called_once()

    async def test_defaults_to_english_when_language_code_missing(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        production_svc = _make_production_service()
        result = await handle_language(
            "produce", {}, track_svc, chunk_svc, wm_svc, production_service=production_svc
        )
        assert result["track_code"] == "en"
        filters = track_svc.get_tracks.call_args[0][0]
        assert filters.code == "en"


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

    async def test_stop_mid_shadowing_returns_feedback_summary(self):
        wm = WorkingMemoryRead(
            id=5, key="language:pending",
            value=json.dumps({
                "mode": "practice", "chunk_id": 10, "track_id": 3,
                "feedback_history": [{"quality_score": 80.0, "summary": "Good"}],
            }),
            importance=1.0, expires_at=None, session_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[wm])
        result = await handle_language("stop", {}, track_svc, chunk_svc, wm_svc)
        wm_svc.delete.assert_called_once_with(5)
        assert result["mode"] == "stopped"
        assert "Good" in result["summary"]

    async def test_stop_mid_shadowing_without_attempts_has_no_summary(self):
        wm = _make_wm_read(id=5, chunk_id=10, mode="practice")
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[wm])
        result = await handle_language("stop", {}, track_svc, chunk_svc, wm_svc)
        wm_svc.delete.assert_called_once_with(5)
        assert result == {"mode": "stopped"}


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

    async def test_practice_resolves_without_language_arg(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/practice")
        assert len(commands) == 1
        assert commands[0].command == "practice"
        assert "language_code" not in commands[0].args

    async def test_review_resolves_without_language_arg(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/review")
        assert len(commands) == 1
        assert commands[0].command == "review"
        assert "language_code" not in commands[0].args

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

    async def test_detect_shadow_alias_maps_to_practice(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/shadow fr")
        assert len(commands) == 1
        assert commands[0].type == "language"
        assert commands[0].command == "practice"
        assert commands[0].args["language_code"] == "fr"

    async def test_detect_produce_command(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/produce es")
        assert len(commands) == 1
        assert commands[0].type == "language"
        assert commands[0].command == "produce"
        assert commands[0].args["language_code"] == "es"

    async def test_detect_produce_alias(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/prod pt")
        assert len(commands) == 1
        assert commands[0].command == "produce"
        assert commands[0].args["language_code"] == "pt"

    async def test_produce_parses_task_type_and_count(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/produce es translate 3")
        assert len(commands) == 1
        assert commands[0].args["language_code"] == "es"
        assert commands[0].args["task_type"] == "translate"
        assert commands[0].args["count"] == "3"

    async def test_produce_resolves_without_language_arg(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/produce")
        assert len(commands) == 1
        assert commands[0].command == "produce"
        assert "language_code" not in commands[0].args

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

    async def test_detect_conversation_command(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/conversation fr talking about food")
        assert len(commands) == 1
        assert commands[0].type == "language"
        assert commands[0].command == "conversation"
        assert commands[0].args["language_code"] == "fr"
        assert commands[0].args["rest"] == "talking about food"

    async def test_conversation_resolves_without_language_arg(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/conversation")
        assert len(commands) == 1
        assert commands[0].command == "conversation"
        assert "language_code" not in commands[0].args

    async def test_detect_roleplay_alias_sets_implicit_mode(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/roleplay fr ordering coffee")
        assert len(commands) == 1
        assert commands[0].type == "language"
        assert commands[0].command == "conversation"
        assert commands[0].args["mode"] == "roleplay"
        assert commands[0].args["language_code"] == "fr"
        assert commands[0].args["rest"] == "ordering coffee"

    async def test_detect_stop_conversation_alias(self):
        from app.assistant.commands.resolver import detect_commands
        commands = await detect_commands("/stop-conversation")
        assert len(commands) == 1
        assert commands[0].command == "stop"


class TestParseCountOrWords:
    def test_numeric_count(self):
        count, words = _parse_count_or_words({"count": "7"})
        assert count == 7
        assert words is None

    def test_missing_count_uses_default(self):
        count, words = _parse_count_or_words({})
        assert count == 5
        assert words is None

    def test_single_word(self):
        count, words = _parse_count_or_words({"count": "cão"})
        assert words == ["cão"]

    def test_multiple_comma_separated_words_are_stripped(self):
        count, words = _parse_count_or_words({"count": "cão,  gato ,peixe"})
        assert words == ["cão", "gato", "peixe"]

    def test_blank_entries_are_dropped(self):
        count, words = _parse_count_or_words({"count": "cão,,gato"})
        assert words == ["cão", "gato"]


class TestResolveLevel:
    def test_valid_level_uppercased(self):
        assert _resolve_level({"level": "a0"}) == "A0"

    def test_missing_level_returns_none(self):
        assert _resolve_level({}) is None

    def test_invalid_level_returns_none(self):
        assert _resolve_level({"level": "z9"}) is None


class TestParseConversationArgs:
    def test_defaults_to_free_conversation_with_voice_on(self):
        mode, topic, voice_reply = _parse_conversation_args("talking about food", None)
        assert mode == "conversation"
        assert topic == "talking about food"
        assert voice_reply is True

    def test_no_topic_is_empty_string(self):
        mode, topic, voice_reply = _parse_conversation_args("", None)
        assert mode == "conversation"
        assert topic == ""
        assert voice_reply is True

    def test_text_keyword_opts_out_of_voice(self):
        mode, topic, voice_reply = _parse_conversation_args("talking about food text", None)
        assert mode == "conversation"
        assert topic == "talking about food"
        assert voice_reply is False

    def test_leading_roleplay_keyword_switches_mode(self):
        mode, scenario, voice_reply = _parse_conversation_args("roleplay ordering coffee", None)
        assert mode == "roleplay"
        assert scenario == "ordering coffee"
        assert voice_reply is False

    def test_roleplay_voice_keyword_opts_in(self):
        mode, scenario, voice_reply = _parse_conversation_args("roleplay ordering coffee voice", None)
        assert mode == "roleplay"
        assert scenario == "ordering coffee"
        assert voice_reply is True

    def test_forced_mode_from_roleplay_alias_treats_rest_as_scenario(self):
        mode, scenario, voice_reply = _parse_conversation_args("ordering coffee", "roleplay")
        assert mode == "roleplay"
        assert scenario == "ordering coffee"
        assert voice_reply is False


def _make_conversation_service(**kwargs):
    service = AsyncMock()
    start_result = kwargs.get("start_result") or MagicMock(
        thread_id=99, track_code="fr", language_name="French", opening_text="Bonjour!", opening_audio_ref=None,
    )
    service.start = AsyncMock(return_value=start_result)
    end_result = kwargs.get("end_result") or MagicMock(tip="Great job!", turn_count=3)
    service.end = AsyncMock(return_value=end_result)
    return service


def _make_language_session_service():
    service = AsyncMock()
    service.record_session = AsyncMock(return_value=MagicMock(id=1))
    return service


class TestHandleStartConversation:
    async def test_free_conversation_starts_a_thread_too(self):
        # Both modes run as tracked threads so turns and end-of-session feedback work
        # the same way for each.
        track_svc, chunk_svc, wm_svc = _make_services()
        conversation_svc = _make_conversation_service()

        result = await handle_language(
            "conversation", {"language_code": "fr", "rest": "talking about food"},
            track_svc, chunk_svc, wm_svc,
            conversation_service=conversation_svc, message_id=1,
        )

        assert result["mode"] == "conversation"
        assert result["topic"] == "talking about food"
        assert result["thread_id"] == 99
        conversation_svc.start.assert_awaited_once_with(
            3, 1, "conversation", "talking about food", True, level_override=None
        )
        wm_value = json.loads(wm_svc.create.call_args[0][0].value)
        assert wm_value["mode"] == "conversation"
        assert wm_value["thread_id"] == 99
        assert wm_value["voice_reply"] is True

    async def test_topicless_conversation_passes_no_topic(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        conversation_svc = _make_conversation_service()

        result = await handle_language(
            "conversation", {"language_code": "fr", "rest": ""},
            track_svc, chunk_svc, wm_svc,
            conversation_service=conversation_svc, message_id=1,
        )

        assert result["topic"] is None
        conversation_svc.start.assert_awaited_once_with(3, 1, "conversation", None, True, level_override=None)

    async def test_roleplay_starts_thread_via_service(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        conversation_svc = _make_conversation_service()

        result = await handle_language(
            "conversation", {"language_code": "fr", "rest": "roleplay ordering coffee"},
            track_svc, chunk_svc, wm_svc,
            conversation_service=conversation_svc, message_id=7,
        )

        conversation_svc.start.assert_awaited_once_with(
            3, 7, "roleplay", "ordering coffee", False, level_override=None
        )
        assert result["mode"] == "roleplay"
        assert result["thread_id"] == 99
        assert result["opening_text"] == "Bonjour!"

    async def test_roleplay_with_level_override(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        conversation_svc = _make_conversation_service()

        await handle_language(
            "conversation", {"language_code": "fr", "rest": "roleplay ordering coffee", "level": "a0"},
            track_svc, chunk_svc, wm_svc,
            conversation_service=conversation_svc, message_id=7,
        )

        conversation_svc.start.assert_awaited_once_with(
            3, 7, "roleplay", "ordering coffee", False, level_override="A0"
        )

    async def test_roleplay_without_scenario_raises_400(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        conversation_svc = _make_conversation_service()

        with pytest.raises(HTTPException) as exc_info:
            await handle_language(
                "conversation", {"language_code": "fr", "rest": "roleplay"},
                track_svc, chunk_svc, wm_svc,
                conversation_service=conversation_svc, message_id=7,
            )
        assert exc_info.value.status_code == 400

    async def test_defaults_to_english_when_language_code_missing(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        conversation_svc = _make_conversation_service()

        result = await handle_language(
            "conversation", {"rest": "talking about food"},
            track_svc, chunk_svc, wm_svc,
            conversation_service=conversation_svc, message_id=1,
        )

        assert result["track_code"] == "en"
        filters = track_svc.get_tracks.call_args[0][0]
        assert filters.code == "en"

    async def test_missing_message_id_raises_400(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        conversation_svc = _make_conversation_service()

        with pytest.raises(HTTPException) as exc_info:
            await handle_language(
                "conversation", {"language_code": "fr", "rest": "hello"},
                track_svc, chunk_svc, wm_svc,
                conversation_service=conversation_svc, message_id=None,
            )
        assert exc_info.value.status_code == 400

    async def test_missing_conversation_service_raises_503(self):
        track_svc, chunk_svc, wm_svc = _make_services()
        with pytest.raises(HTTPException) as exc_info:
            await handle_language(
                "conversation", {"language_code": "fr", "rest": "hello"},
                track_svc, chunk_svc, wm_svc,
                message_id=1,
            )
        assert exc_info.value.status_code == 503


class TestHandleStopConversationModes:
    async def test_stop_ends_roleplay_thread(self):
        wm = WorkingMemoryRead(
            id=8, key="language:pending",
            value=json.dumps({"mode": "roleplay", "track_id": 3, "thread_id": 99}),
            importance=1.0, expires_at=None, session_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[wm])
        conversation_svc = _make_conversation_service()

        result = await handle_language(
            "stop", {}, track_svc, chunk_svc, wm_svc, conversation_service=conversation_svc,
        )

        conversation_svc.end.assert_awaited_once_with(99)
        assert result["mode"] == "stopped"
        assert result["tip"] == "Great job!"
        assert result["turn_count"] == 3
        wm_svc.delete.assert_called_once_with(8)

    async def test_stop_ends_free_conversation_thread_with_feedback(self):
        # Free conversation gets the same end-of-session coaching feedback as roleplay.
        wm = WorkingMemoryRead(
            id=9, key="language:pending",
            value=json.dumps({"mode": "conversation", "track_id": 3, "thread_id": 77}),
            importance=1.0, expires_at=None, session_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        track_svc, chunk_svc, wm_svc = _make_services(existing_wm=[wm])
        conversation_svc = _make_conversation_service()

        result = await handle_language(
            "stop", {}, track_svc, chunk_svc, wm_svc, conversation_service=conversation_svc,
        )

        conversation_svc.end.assert_awaited_once_with(77)
        assert result["mode"] == "stopped"
        assert result["tip"] == "Great job!"
        assert result["turn_count"] == 3
        wm_svc.delete.assert_called_once_with(9)
