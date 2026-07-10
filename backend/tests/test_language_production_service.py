import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.features.language.production.schemas import ProductionAttemptCreate
from app.features.language.production.service import (
    ProductionService,
    _build_prompt_text,
    _next_task_type,
    _parse_grading_json,
)
from app.features.language.srs import score_to_quality


def _make_chunk_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 42)
    orm.track_id = kwargs.get("track_id", 1)
    orm.text = kwargs.get("text", "parler de quelque chose")
    orm.translation = kwargs.get("translation", "to talk about something")
    orm.example_sentence = kwargs.get("example_sentence", None)
    orm.example_translation = kwargs.get("example_translation", None)
    orm.cefr_level = kwargs.get("cefr_level", "B1")
    return orm


def _make_chunk_read(**kwargs):
    chunk = MagicMock()
    chunk.id = kwargs.get("id", 42)
    chunk.text = kwargs.get("text", "parler de quelque chose")
    chunk.translation = kwargs.get("translation", "to talk about something")
    chunk.example_sentence = kwargs.get("example_sentence", None)
    chunk.example_translation = kwargs.get("example_translation", None)
    return chunk


def _make_track_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.code = kwargs.get("code", "fr")
    orm.name = kwargs.get("name", "French")
    orm.level = kwargs.get("level", "B1")
    orm.active = kwargs.get("active", True)
    return orm


def _make_batch(chunks, total_due=None):
    batch = MagicMock()
    batch.chunks = chunks
    batch.total_due = total_due if total_due is not None else len(chunks)
    return batch


_GRADING_JSON = json.dumps({
    "score": 80,
    "errors": ["wrong article"],
    "corrected_text": "Je parle de la musique.",
    "feedback": "Almost perfect!",
    "new_vocabulary": [{"text": "la musique", "translation": "music"}],
})


def _make_llm_provider(text: str = _GRADING_JSON):
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-2.0-flash"
    response = MagicMock()
    response.text = text
    response.tokens_input = 100
    response.tokens_output = 50
    provider.complete = AsyncMock(return_value=response)
    return provider


def _make_service(llm_text: str = _GRADING_JSON):
    session = AsyncMock()
    llm_provider = _make_llm_provider(llm_text)
    session_service = AsyncMock()
    session_service.record_production.return_value = MagicMock(id=7)
    chunk_service = AsyncMock()
    chunk_repo = AsyncMock()
    track_repo = AsyncMock()
    session_repo = AsyncMock()
    service = ProductionService(
        session=session,
        llm_provider=llm_provider,
        session_service=session_service,
        chunk_service=chunk_service,
        chunk_repo=chunk_repo,
        track_repo=track_repo,
        session_repo=session_repo,
    )
    return service, llm_provider, session_service, chunk_service, chunk_repo, track_repo, session_repo


def _make_attempt(**kwargs) -> ProductionAttemptCreate:
    return ProductionAttemptCreate(
        track_id=kwargs.get("track_id", 1),
        chunk_id=kwargs.get("chunk_id", 42),
        task_type=kwargs.get("task_type", "sentence"),
        prompt_text=kwargs.get("prompt_text", "Write a sentence using X"),
        response_text=kwargs.get("response_text", "Je parle de le musique."),
    )


class TestNextTaskType:
    def test_starts_with_sentence_when_no_history(self):
        assert _next_task_type(None) == "sentence"

    def test_rotates_sentence_to_translate(self):
        assert _next_task_type("sentence") == "translate"

    def test_rotates_translate_back_to_sentence(self):
        assert _next_task_type("translate") == "sentence"

    def test_unknown_last_type_falls_back_to_first(self):
        assert _next_task_type("journal") == "sentence"


class TestBuildPromptText:
    def test_sentence_prompt_includes_chunk_and_translation(self):
        chunk = _make_chunk_read()
        prompt = _build_prompt_text("sentence", "French", chunk)
        assert "parler de quelque chose" in prompt
        assert "to talk about something" in prompt
        assert "French" in prompt

    def test_translate_prompt_uses_example_translation(self):
        chunk = _make_chunk_read(example_translation="We talked about the trip.")
        prompt = _build_prompt_text("translate", "French", chunk)
        assert "We talked about the trip." in prompt
        assert "French" in prompt

    def test_translate_prompt_falls_back_to_chunk_translation(self):
        chunk = _make_chunk_read(example_translation=None)
        prompt = _build_prompt_text("translate", "French", chunk)
        assert "to talk about something" in prompt


class TestParseGradingJson:
    def test_parses_plain_json(self):
        grading = _parse_grading_json(_GRADING_JSON)
        assert grading.score == 80
        assert grading.errors == ["wrong article"]
        assert grading.corrected_text == "Je parle de la musique."
        assert grading.new_vocabulary[0].text == "la musique"

    def test_parses_json_wrapped_in_markdown_fences(self):
        grading = _parse_grading_json(f"```json\n{_GRADING_JSON}\n```")
        assert grading.score == 80

    def test_defaults_for_missing_fields(self):
        grading = _parse_grading_json('{"score": 55}')
        assert grading.score == 55
        assert grading.errors == []
        assert grading.corrected_text == ""
        assert grading.new_vocabulary == []

    def test_skips_vocabulary_entries_without_text(self):
        raw = json.dumps({"score": 70, "new_vocabulary": [{"translation": "orphan"}, "junk"]})
        grading = _parse_grading_json(raw)
        assert grading.new_vocabulary == []

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_grading_json("not json at all")


class TestGetNextTask:
    async def test_builds_task_for_first_due_chunk(self):
        service, _, _, chunk_service, _, track_repo, session_repo = _make_service()
        track_repo.get_track.return_value = _make_track_orm()
        chunk_service.get_production_daily_batch.return_value = [
            _make_batch([_make_chunk_read(id=42)], total_due=4)
        ]
        session_repo.get_last_production_task_type.return_value = None

        task = await service.get_next_task(1)

        assert task is not None
        assert task.chunk_id == 42
        assert task.task_type == "sentence"
        assert task.track_code == "fr"
        assert task.language_name == "French"
        assert task.total_due == 4
        assert "parler de quelque chose" in task.prompt_text

    async def test_rotates_task_type_from_last_session(self):
        service, _, _, chunk_service, _, track_repo, session_repo = _make_service()
        track_repo.get_track.return_value = _make_track_orm()
        chunk_service.get_production_daily_batch.return_value = [_make_batch([_make_chunk_read()])]
        session_repo.get_last_production_task_type.return_value = "sentence"

        task = await service.get_next_task(1)

        assert task.task_type == "translate"

    async def test_explicit_task_type_skips_rotation(self):
        service, _, _, chunk_service, _, track_repo, session_repo = _make_service()
        track_repo.get_track.return_value = _make_track_orm()
        chunk_service.get_production_daily_batch.return_value = [_make_batch([_make_chunk_read()])]

        task = await service.get_next_task(1, task_type="translate")

        assert task.task_type == "translate"
        session_repo.get_last_production_task_type.assert_not_called()

    async def test_excludes_given_chunk_id(self):
        service, _, _, chunk_service, _, track_repo, session_repo = _make_service()
        track_repo.get_track.return_value = _make_track_orm()
        chunk_service.get_production_daily_batch.return_value = [
            _make_batch([_make_chunk_read(id=42), _make_chunk_read(id=43, text="autre chose")])
        ]
        session_repo.get_last_production_task_type.return_value = None

        task = await service.get_next_task(1, exclude_chunk_id=42)

        assert task.chunk_id == 43

    async def test_returns_none_when_no_due_chunks(self):
        service, _, _, chunk_service, _, track_repo, _ = _make_service()
        track_repo.get_track.return_value = _make_track_orm()
        chunk_service.get_production_daily_batch.return_value = [_make_batch([])]

        assert await service.get_next_task(1) is None

    async def test_returns_none_when_track_missing(self):
        service, _, _, _, _, track_repo, _ = _make_service()
        track_repo.get_track.return_value = None

        assert await service.get_next_task(99) is None


class TestGradeAttempt:
    async def test_happy_path_records_session_and_returns_grading(self):
        service, llm_provider, session_service, _, chunk_repo, track_repo, _ = _make_service()
        chunk_repo.get_chunk.return_value = _make_chunk_orm()
        track_repo.get_track.return_value = _make_track_orm()

        with patch("app.features.language.production.service.create_llm_call", AsyncMock()) as mock_log:
            result = await service.grade_attempt(_make_attempt())

        assert result.session_id == 7
        assert result.quality_score == score_to_quality(80)
        assert result.grading.score == 80
        assert result.grading.corrected_text == "Je parle de la musique."

        record_call = session_service.record_production.call_args.args[0]
        assert record_call.track_id == 1
        assert record_call.chunk_id == 42
        assert record_call.task_type == "sentence"
        assert record_call.prompt_text == "Write a sentence using X"
        assert record_call.quality_score == score_to_quality(80)
        assert record_call.transcript_or_notes == "Je parle de le musique."
        assert record_call.ai_feedback_json["score"] == 80

        mock_log.assert_awaited_once()
        assert mock_log.call_args.kwargs["feature"] == "production_grading"

    async def test_queues_new_vocabulary_for_triage(self):
        service, _, _, chunk_service, chunk_repo, track_repo, _ = _make_service()
        chunk_repo.get_chunk.return_value = _make_chunk_orm()
        track_repo.get_track.return_value = _make_track_orm()

        with patch("app.features.language.production.service.create_llm_call", AsyncMock()):
            await service.grade_attempt(_make_attempt())

        chunk_service.create_chunk.assert_awaited_once()
        created = chunk_service.create_chunk.call_args.args[0]
        assert created.text == "la musique"
        assert created.translation == "music"
        assert created.status == "pending_triage"
        assert created.frequency_source == "llm_suggested"

    async def test_limits_vocabulary_candidates_to_three(self):
        vocab = [{"text": f"mot{i}", "translation": f"word{i}"} for i in range(5)]
        raw = json.dumps({"score": 60, "new_vocabulary": vocab})
        service, _, _, chunk_service, chunk_repo, track_repo, _ = _make_service(llm_text=raw)
        chunk_repo.get_chunk.return_value = _make_chunk_orm()
        track_repo.get_track.return_value = _make_track_orm()

        with patch("app.features.language.production.service.create_llm_call", AsyncMock()):
            await service.grade_attempt(_make_attempt())

        assert chunk_service.create_chunk.await_count == 3

    async def test_vocabulary_failure_does_not_fail_attempt(self):
        service, _, _, chunk_service, chunk_repo, track_repo, _ = _make_service()
        chunk_repo.get_chunk.return_value = _make_chunk_orm()
        track_repo.get_track.return_value = _make_track_orm()
        chunk_service.create_chunk.side_effect = RuntimeError("db boom")

        with patch("app.features.language.production.service.create_llm_call", AsyncMock()):
            result = await service.grade_attempt(_make_attempt())

        assert result.session_id == 7

    async def test_translate_task_includes_reference_answer_in_prompt(self):
        service, llm_provider, _, _, chunk_repo, track_repo, _ = _make_service()
        chunk_repo.get_chunk.return_value = _make_chunk_orm(example_sentence="Nous avons parlé du voyage.")
        track_repo.get_track.return_value = _make_track_orm()

        with patch("app.features.language.production.service.create_llm_call", AsyncMock()):
            await service.grade_attempt(_make_attempt(task_type="translate"))

        prompt = llm_provider.complete.call_args.args[0][0]["content"]
        assert "Nous avons parlé du voyage." in prompt

    async def test_raises_404_when_chunk_missing(self):
        service, _, _, _, chunk_repo, _, _ = _make_service()
        chunk_repo.get_chunk.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.grade_attempt(_make_attempt())
        assert exc_info.value.status_code == 404

    async def test_raises_503_when_llm_fails(self):
        service, llm_provider, _, _, chunk_repo, track_repo, _ = _make_service()
        chunk_repo.get_chunk.return_value = _make_chunk_orm()
        track_repo.get_track.return_value = _make_track_orm()
        llm_provider.complete.side_effect = RuntimeError("gemini boom")

        with pytest.raises(HTTPException) as exc_info:
            await service.grade_attempt(_make_attempt())
        assert exc_info.value.status_code == 503

    async def test_raises_502_on_unparseable_grading(self):
        service, _, session_service, _, chunk_repo, track_repo, _ = _make_service(llm_text="sorry, no json")
        chunk_repo.get_chunk.return_value = _make_chunk_orm()
        track_repo.get_track.return_value = _make_track_orm()

        with patch("app.features.language.production.service.create_llm_call", AsyncMock()):
            with pytest.raises(HTTPException) as exc_info:
                await service.grade_attempt(_make_attempt())
        assert exc_info.value.status_code == 502
        session_service.record_production.assert_not_called()


class TestGetMastery:
    async def test_aggregates_recognition_and_production_counts(self):
        service, _, _, _, chunk_repo, track_repo, _ = _make_service()
        track_repo.get_tracks.return_value = [_make_track_orm(id=1, code="fr")]
        chunk_repo.count_by_state_for_track.side_effect = [
            {"new": 5, "learning": 3, "review": 10},          # recognition
            {"new": 12, "learning": 2, "review": 4},          # production
        ]
        chunk_repo.count_production_locked_for_track.return_value = 8
        chunk_repo.count_due_for_track.return_value = 6
        chunk_repo.count_production_due_for_track.return_value = 2

        result = await service.get_mastery()

        assert len(result) == 1
        mastery = result[0]
        assert mastery.total_active == 18
        assert mastery.recognition.new == 5
        assert mastery.recognition.review == 10
        assert mastery.recognition.due == 6
        # locked chunks are excluded from the production "new" bucket
        assert mastery.production.new == 4
        assert mastery.production.due == 2
        assert mastery.production_locked == 8

    async def test_filters_by_track_id(self):
        service, _, _, _, chunk_repo, track_repo, _ = _make_service()
        track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr"),
            _make_track_orm(id=2, code="ru"),
        ]
        chunk_repo.count_by_state_for_track.return_value = {}
        chunk_repo.count_production_locked_for_track.return_value = 0
        chunk_repo.count_due_for_track.return_value = 0
        chunk_repo.count_production_due_for_track.return_value = 0

        result = await service.get_mastery(track_id=2)

        assert len(result) == 1
        assert result[0].track_id == 2
