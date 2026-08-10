import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.features.language.chunks.service import ChunkService
from app.features.language.chunks.schemas import ChunkCreate, ChunkFilters, ChunkUpdate, NewVocabularyCandidate


def _make_chunk_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.track_id = kwargs.get("track_id", 1)
    orm.grammar_scope_id = kwargs.get("grammar_scope_id", None)
    orm.chunk_type = kwargs.get("chunk_type", "collocation")
    orm.text = kwargs.get("text", "parler de quelque chose")
    orm.translation = kwargs.get("translation", "to talk about something")
    orm.example_sentence = kwargs.get("example_sentence", None)
    orm.example_translation = kwargs.get("example_translation", None)
    orm.cefr_level = kwargs.get("cefr_level", "B1")
    orm.frequency_rank = kwargs.get("frequency_rank", 500)
    orm.frequency_source = kwargs.get("frequency_source", "pareto_list")
    orm.stability = kwargs.get("stability", 0.0)
    orm.difficulty = kwargs.get("difficulty", 5.0)
    orm.due_at = kwargs.get("due_at", datetime(2026, 6, 25, tzinfo=timezone.utc))
    orm.last_review_at = kwargs.get("last_review_at", None)
    orm.repetitions = kwargs.get("repetitions", 0)
    orm.lapses = kwargs.get("lapses", 0)
    orm.consecutive_failures = kwargs.get("consecutive_failures", 0)
    orm.state = kwargs.get("state", "new")
    orm.prod_stability = kwargs.get("prod_stability", 0.0)
    orm.prod_difficulty = kwargs.get("prod_difficulty", 5.0)
    orm.prod_due_at = kwargs.get("prod_due_at", None)
    orm.prod_last_review_at = kwargs.get("prod_last_review_at", None)
    orm.prod_repetitions = kwargs.get("prod_repetitions", 0)
    orm.prod_lapses = kwargs.get("prod_lapses", 0)
    orm.prod_consecutive_failures = kwargs.get("prod_consecutive_failures", 0)
    orm.prod_state = kwargs.get("prod_state", "new")
    orm.status = kwargs.get("status", "active")
    orm.is_leech = kwargs.get("is_leech", False)
    orm.created_at = kwargs.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    orm.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return orm


def _make_track_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.code = kwargs.get("code", "fr")
    orm.name = kwargs.get("name", "French")
    orm.level = kwargs.get("level", "B1")
    orm.daily_quota = kwargs.get("daily_quota", 10)
    orm.active = kwargs.get("active", True)
    return orm


_ENRICHMENT_JSON = '{"chunk_type": "word", "translation": "dog", "example_sentence": "Le chien court.", ' \
    '"example_translation": "The dog runs.", "cefr_level": "A1"}'


def _make_llm_provider(text: str = _ENRICHMENT_JSON):
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-2.0-flash"
    response = MagicMock()
    response.text = text
    response.tokens_input = 20
    response.tokens_output = 10
    response.finish_reason = "STOP"
    provider.complete = AsyncMock(return_value=response)
    return provider


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    svc = ChunkService(session=mock_session)
    svc._repo = AsyncMock()
    svc._track_repo = AsyncMock()
    return svc


class TestGetChunk:
    async def test_returns_chunk_read_when_found(self, service):
        service._repo.get_chunk.return_value = _make_chunk_orm()
        result = await service.get_chunk(1)
        assert result is not None
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_chunk.return_value = None
        result = await service.get_chunk(999)
        assert result is None


class TestCreateChunk:
    async def test_creates_and_returns_chunk_read(self, service):
        data = ChunkCreate(
            track_id=1,
            chunk_type="collocation",
            text="parler de quelque chose",
            translation="to talk about something",
        )
        service._repo.create_chunk.return_value = _make_chunk_orm()
        result = await service.create_chunk(data)
        service._repo.create_chunk.assert_called_once_with(data)
        assert result.text == "parler de quelque chose"


class TestApproveChunk:
    async def test_sets_status_to_active(self, service):
        service._repo.get_chunk.return_value = _make_chunk_orm(status="pending_triage")
        service._repo.update_chunk.return_value = _make_chunk_orm(status="active")
        result = await service.approve_chunk(1)
        assert result is not None
        update_call = service._repo.update_chunk.call_args
        assert update_call[0][1].status == "active"

    async def test_returns_none_when_chunk_not_found(self, service):
        service._repo.get_chunk.return_value = None
        result = await service.approve_chunk(999)
        assert result is None


class TestApplySrsReview:
    async def test_updates_srs_fields_after_good_review(self, service):
        chunk = _make_chunk_orm(state="new", stability=0.0)
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm(state="learning", stability=3.0)]
        result = await service.apply_srs_review(1, quality_score=3.5)
        assert service._repo.update_srs_fields.called

    async def test_returns_none_when_chunk_not_found(self, service):
        service._repo.get_chunk.return_value = None
        result = await service.apply_srs_review(999, quality_score=3.0)
        assert result is None

    async def test_increments_lapses_on_again_rating(self, service):
        chunk = _make_chunk_orm(state="review", stability=10.0, lapses=0)
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm(lapses=1)]
        await service.apply_srs_review(1, quality_score=0.5)
        update_kwargs = service._repo.update_srs_fields.call_args[1]
        assert update_kwargs["lapses"] == 1

    async def test_flags_leech_after_threshold_failures(self, service):
        chunk = _make_chunk_orm(
            state="review",
            stability=5.0,
            consecutive_failures=7,
        )
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm(is_leech=True)]
        await service.apply_srs_review(1, quality_score=0.0)
        update_kwargs = service._repo.update_srs_fields.call_args[1]
        assert update_kwargs["is_leech"] is True

    async def test_unlocks_production_on_first_successful_review(self, service):
        chunk = _make_chunk_orm(state="new", prod_due_at=None)
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm()]
        await service.apply_srs_review(1, quality_score=3.0)
        service._repo.unlock_production.assert_called_once()
        assert service._repo.unlock_production.call_args[0][0] == 1

    async def test_does_not_unlock_production_on_failed_review(self, service):
        chunk = _make_chunk_orm(state="new", prod_due_at=None)
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm()]
        await service.apply_srs_review(1, quality_score=1.0)
        service._repo.unlock_production.assert_not_called()

    async def test_does_not_unlock_production_when_already_unlocked(self, service):
        chunk = _make_chunk_orm(
            state="review",
            stability=5.0,
            prod_due_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm()]
        await service.apply_srs_review(1, quality_score=3.5)
        service._repo.unlock_production.assert_not_called()


class TestApplyProductionReview:
    async def test_updates_production_fields_only(self, service):
        chunk = _make_chunk_orm(
            prod_state="new",
            prod_due_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        )
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm(prod_state="learning")]
        result = await service.apply_production_review(1, quality_score=3.0)
        assert result is not None
        service._repo.update_production_srs_fields.assert_called_once()
        service._repo.update_srs_fields.assert_not_called()

    async def test_uses_production_card_state(self, service):
        chunk = _make_chunk_orm(
            state="review",
            stability=50.0,
            prod_state="new",
            prod_stability=0.0,
            prod_due_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        )
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm()]
        await service.apply_production_review(1, quality_score=3.0)
        update_kwargs = service._repo.update_production_srs_fields.call_args[1]
        # A "new" production card starts learning regardless of the recognition state
        assert update_kwargs["state"] == "learning"
        assert update_kwargs["repetitions"] == 1

    async def test_increments_production_lapses_on_again_rating(self, service):
        chunk = _make_chunk_orm(
            prod_state="review",
            prod_stability=10.0,
            prod_lapses=2,
            prod_due_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
            prod_last_review_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        )
        service._repo.get_chunk.side_effect = [chunk, _make_chunk_orm()]
        await service.apply_production_review(1, quality_score=1.0)
        update_kwargs = service._repo.update_production_srs_fields.call_args[1]
        assert update_kwargs["lapses"] == 3

    async def test_returns_none_when_chunk_not_found(self, service):
        service._repo.get_chunk.return_value = None
        service._repo.get_chunk.side_effect = None
        result = await service.apply_production_review(999, quality_score=3.0)
        assert result is None


class TestCountChunks:
    async def test_returns_count_from_repo(self, service):
        service._repo.count_chunks.return_value = 42
        filters = ChunkFilters(track_id=1, status="active")
        result = await service.count_chunks(filters)
        service._repo.count_chunks.assert_called_once_with(filters)
        assert result == 42

    async def test_returns_zero_when_no_chunks(self, service):
        service._repo.count_chunks.return_value = 0
        filters = ChunkFilters(track_id=99, status="active")
        result = await service.count_chunks(filters)
        assert result == 0


class TestShiftDueDates:
    async def test_delegates_to_repo(self, service):
        delta = timedelta(days=2)
        await service.shift_due_dates(1, delta)
        service._repo.shift_due_dates.assert_called_once_with(1, delta)


class TestGetDailyBatch:
    async def test_returns_batch_per_active_track(self, service):
        service._track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr", daily_quota=5),
            _make_track_orm(id=2, code="ru", daily_quota=5),
        ]
        service._repo.count_due_for_track.return_value = 3
        service._repo.get_due_chunks_for_track.return_value = [_make_chunk_orm()] * 3

        result = await service.get_daily_batch()

        assert len(result) == 2
        assert result[0].track_code == "fr"
        assert result[0].total_due == 3
        assert len(result[0].chunks) == 3

    async def test_filters_by_track_id_when_provided(self, service):
        service._track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr"),
            _make_track_orm(id=2, code="ru"),
        ]
        service._repo.count_due_for_track.return_value = 2
        service._repo.get_due_chunks_for_track.return_value = []

        result = await service.get_daily_batch(track_id=1)

        assert len(result) == 1
        assert result[0].track_id == 1


class TestGetProductionDailyBatch:
    async def test_returns_production_due_batch_per_track(self, service):
        service._track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr", daily_quota=5),
        ]
        service._repo.count_production_due_for_track.return_value = 2
        service._repo.get_production_due_chunks_for_track.return_value = [_make_chunk_orm()] * 2

        result = await service.get_production_daily_batch()

        assert len(result) == 1
        assert result[0].total_due == 2
        assert len(result[0].chunks) == 2
        service._repo.get_production_due_chunks_for_track.assert_called_once_with(1, 5)

    async def test_filters_by_track_id_when_provided(self, service):
        service._track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr"),
            _make_track_orm(id=2, code="ru"),
        ]
        service._repo.count_production_due_for_track.return_value = 0
        service._repo.get_production_due_chunks_for_track.return_value = []

        result = await service.get_production_daily_batch(track_id=2)

        assert len(result) == 1
        assert result[0].track_id == 2


class TestForcePracticeChunks:
    async def test_returns_existing_chunk_without_llm_call(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = _make_chunk_orm(text="chien", translation="dog")

        result = await service.force_practice_chunks(1, ["chien"])

        assert result[0].text == "chien"
        service._repo.create_chunk.assert_not_called()

    async def test_creates_new_chunk_via_llm_enrichment(self, service):
        service._llm_provider = _make_llm_provider()
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.return_value = _make_chunk_orm(text="chien", translation="dog")

        with patch("app.features.language.chunks.service.create_llm_call", AsyncMock()):
            result = await service.force_practice_chunks(1, ["chien"])

        assert result[0].text == "chien"
        created = service._repo.create_chunk.call_args.args[0]
        assert created.text == "chien"
        assert created.translation == "dog"
        assert created.status == "active"
        assert created.frequency_source == "user_requested"
        assert created.cefr_level == "A1"

    async def test_logs_finish_reason_to_llm_calls(self, service):
        service._llm_provider = _make_llm_provider()
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.return_value = _make_chunk_orm(text="chien", translation="dog")

        with patch("app.features.language.chunks.service.create_llm_call", AsyncMock()) as mock_log:
            await service.force_practice_chunks(1, ["chien"])

        assert mock_log.call_args.kwargs["finish_reason"] == "STOP"

    async def test_missing_cefr_level_falls_back_to_track_level(self, service):
        service._llm_provider = _make_llm_provider(
            '{"chunk_type": "word", "translation": "dog"}'
        )
        service._track_repo.get_track.return_value = _make_track_orm(level="B2")
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.return_value = _make_chunk_orm()

        with patch("app.features.language.chunks.service.create_llm_call", AsyncMock()):
            await service.force_practice_chunks(1, ["chien"])

        created = service._repo.create_chunk.call_args.args[0]
        assert created.cefr_level == "B2"

    async def test_level_override_steers_enrichment_prompt(self, service):
        llm = _make_llm_provider()
        service._llm_provider = llm
        service._track_repo.get_track.return_value = _make_track_orm(level="B1")
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.return_value = _make_chunk_orm()

        with patch("app.features.language.chunks.service.create_llm_call", AsyncMock()):
            await service.force_practice_chunks(1, ["chien"], level_override="A0")

        prompt = llm.complete.call_args.args[0][0]["content"]
        assert "essentially no French yet" in prompt  # A0 guidance line, not B1's

    async def test_raises_503_when_llm_unavailable_and_chunk_missing(self, service):
        service._llm_provider = None
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.force_practice_chunks(1, ["chien"])
        assert exc_info.value.status_code == 503

    async def test_raises_404_when_track_not_found(self, service):
        service._track_repo.get_track.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.force_practice_chunks(1, ["chien"])
        assert exc_info.value.status_code == 404

    async def test_dedupes_case_insensitively(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = _make_chunk_orm()

        await service.force_practice_chunks(1, ["Chien", "chien", " chien "])

        assert service._repo.get_chunk_by_text.await_count == 1

    async def test_raises_400_when_no_valid_texts(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()

        with pytest.raises(HTTPException) as exc_info:
            await service.force_practice_chunks(1, ["", "  "])
        assert exc_info.value.status_code == 400


class TestQueueVocabularyCandidates:
    async def test_creates_pending_triage_chunk_per_candidate(self, service):
        service._track_repo.get_track.return_value = _make_track_orm(level="B1")
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.return_value = _make_chunk_orm()

        await service.queue_vocabulary_candidates(
            1, [NewVocabularyCandidate(text="chien", translation="dog", cefr_level="A1")], max_candidates=3
        )

        created = service._repo.create_chunk.call_args.args[0]
        assert created.text == "chien"
        assert created.status == "pending_triage"
        assert created.frequency_source == "llm_suggested"
        assert created.cefr_level == "A1"

    async def test_missing_candidate_level_falls_back_to_track_level(self, service):
        service._track_repo.get_track.return_value = _make_track_orm(level="B2")
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.return_value = _make_chunk_orm()

        await service.queue_vocabulary_candidates(
            1, [NewVocabularyCandidate(text="chien", translation="dog")], max_candidates=3
        )

        created = service._repo.create_chunk.call_args.args[0]
        assert created.cefr_level == "B2"

    async def test_respects_max_candidates(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.return_value = _make_chunk_orm()
        candidates = [NewVocabularyCandidate(text=f"mot{i}", translation=f"word{i}") for i in range(5)]

        await service.queue_vocabulary_candidates(1, candidates, max_candidates=2)

        assert service._repo.create_chunk.await_count == 2

    async def test_skips_candidates_with_blank_text_or_translation(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        candidates = [
            NewVocabularyCandidate(text="", translation="dog"),
            NewVocabularyCandidate(text="chien", translation=""),
        ]

        await service.queue_vocabulary_candidates(1, candidates, max_candidates=5)

        service._repo.create_chunk.assert_not_called()

    async def test_individual_failure_does_not_stop_remaining_candidates(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = None
        service._repo.create_chunk.side_effect = [RuntimeError("db boom"), _make_chunk_orm()]
        candidates = [
            NewVocabularyCandidate(text="chien", translation="dog"),
            NewVocabularyCandidate(text="chat", translation="cat"),
        ]

        await service.queue_vocabulary_candidates(1, candidates, max_candidates=5)

        assert service._repo.create_chunk.await_count == 2

    async def test_skips_candidate_matching_existing_active_chunk(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = _make_chunk_orm(
            id=42, text="chien", status="active"
        )

        await service.queue_vocabulary_candidates(
            1, [NewVocabularyCandidate(text="chien", translation="dog")], max_candidates=5
        )

        service._repo.get_chunk_by_text.assert_awaited_once_with(1, "chien")
        service._repo.create_chunk.assert_not_called()

    async def test_skips_candidate_already_pending_triage(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.return_value = _make_chunk_orm(
            id=42, text="chien", status="pending_triage"
        )

        await service.queue_vocabulary_candidates(
            1, [NewVocabularyCandidate(text="chien", translation="dog")], max_candidates=5
        )

        service._repo.create_chunk.assert_not_called()

    async def test_creates_remaining_candidates_when_only_one_is_duplicate(self, service):
        service._track_repo.get_track.return_value = _make_track_orm()
        service._repo.get_chunk_by_text.side_effect = [
            _make_chunk_orm(id=42, text="chien", status="active"),
            None,
        ]
        service._repo.create_chunk.return_value = _make_chunk_orm(text="chat")
        candidates = [
            NewVocabularyCandidate(text="chien", translation="dog"),
            NewVocabularyCandidate(text="chat", translation="cat"),
        ]

        await service.queue_vocabulary_candidates(1, candidates, max_candidates=5)

        assert service._repo.create_chunk.await_count == 1
        created = service._repo.create_chunk.call_args.args[0]
        assert created.text == "chat"
