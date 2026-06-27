import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone

from app.features.language.chunks.service import ChunkService
from app.features.language.chunks.schemas import ChunkCreate, ChunkFilters, ChunkUpdate


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
    orm.status = kwargs.get("status", "active")
    orm.is_leech = kwargs.get("is_leech", False)
    orm.created_at = kwargs.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    orm.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return orm


def _make_track_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.code = kwargs.get("code", "fr")
    orm.daily_quota = kwargs.get("daily_quota", 10)
    orm.active = kwargs.get("active", True)
    return orm


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
