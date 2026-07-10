import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from app.features.language.sessions.service import SessionService
from app.features.language.sessions.schemas import (
    ProductionSessionCreate,
    SrsReviewCreate,
    ShadowingSessionCreate,
    SessionCreate,
    SessionFilters,
)


def _make_session_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.track_id = kwargs.get("track_id", 1)
    orm.chunk_id = kwargs.get("chunk_id", 10)
    orm.session_type = kwargs.get("session_type", "srs_review")
    orm.task_type = kwargs.get("task_type", None)
    orm.prompt_text = kwargs.get("prompt_text", None)
    orm.feeds_srs = kwargs.get("feeds_srs", True)
    orm.audio_ref = kwargs.get("audio_ref", None)
    orm.ai_feedback_json = kwargs.get("ai_feedback_json", None)
    orm.quality_score = kwargs.get("quality_score", 3.5)
    orm.transcript_or_notes = kwargs.get("transcript_or_notes", None)
    orm.created_at = kwargs.get("created_at", datetime(2026, 6, 25, tzinfo=timezone.utc))
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
    svc = SessionService(session=mock_session)
    svc._repo = AsyncMock()
    svc._track_repo = AsyncMock()
    svc._chunk_service = AsyncMock()
    return svc


class TestRecordSrsReview:
    async def test_creates_session_and_updates_chunk(self, service):
        service._repo.create_session.return_value = _make_session_orm()
        data = SrsReviewCreate(track_id=1, chunk_id=10, quality_score=3.5)

        result = await service.record_srs_review(data)

        service._repo.create_session.assert_called_once()
        call_kwargs = service._repo.create_session.call_args[1]
        assert call_kwargs["session_type"] == "srs_review"
        assert call_kwargs["feeds_srs"] is True
        assert call_kwargs["quality_score"] == 3.5

        service._chunk_service.apply_srs_review.assert_called_once_with(10, 3.5)
        assert result.id == 1

    async def test_session_type_is_srs_review(self, service):
        service._repo.create_session.return_value = _make_session_orm(session_type="srs_review")
        data = SrsReviewCreate(track_id=1, chunk_id=5, quality_score=4.0)
        result = await service.record_srs_review(data)
        assert result.session_type == "srs_review"


class TestRecordShadowing:
    async def test_creates_session_with_audio_ref(self, service):
        service._repo.create_session.return_value = _make_session_orm(
            session_type="shadowing", audio_ref="language/fr/session_1.ogg"
        )
        data = ShadowingSessionCreate(track_id=1, chunk_id=10, quality_score=4.0)

        result = await service.record_shadowing(data, audio_ref="language/fr/session_1.ogg")

        call_kwargs = service._repo.create_session.call_args[1]
        assert call_kwargs["session_type"] == "shadowing"
        assert call_kwargs["audio_ref"] == "language/fr/session_1.ogg"

    async def test_updates_srs_when_quality_score_provided(self, service):
        service._repo.create_session.return_value = _make_session_orm(session_type="shadowing")
        data = ShadowingSessionCreate(track_id=1, chunk_id=10, quality_score=3.0)

        await service.record_shadowing(data)

        service._chunk_service.apply_srs_review.assert_called_once_with(10, 3.0)

    async def test_skips_srs_update_when_no_quality_score(self, service):
        service._repo.create_session.return_value = _make_session_orm(session_type="shadowing")
        data = ShadowingSessionCreate(track_id=1, chunk_id=10, quality_score=None)

        await service.record_shadowing(data)

        service._chunk_service.apply_srs_review.assert_not_called()


class TestRecordProduction:
    async def test_creates_production_session_and_updates_production_srs(self, service):
        service._repo.create_session.return_value = _make_session_orm(
            session_type="production", task_type="sentence", prompt_text="Write a sentence"
        )
        data = ProductionSessionCreate(
            track_id=1, chunk_id=10, task_type="sentence",
            prompt_text="Write a sentence", quality_score=3.2,
        )

        result = await service.record_production(data)

        call_kwargs = service._repo.create_session.call_args[1]
        assert call_kwargs["session_type"] == "production"
        assert call_kwargs["task_type"] == "sentence"
        assert call_kwargs["prompt_text"] == "Write a sentence"
        assert call_kwargs["feeds_srs"] is True
        service._chunk_service.apply_production_review.assert_called_once_with(10, 3.2)
        service._chunk_service.apply_srs_review.assert_not_called()
        assert result.session_type == "production"

    async def test_skips_srs_update_when_no_quality_score(self, service):
        service._repo.create_session.return_value = _make_session_orm(
            session_type="production", task_type="translate", feeds_srs=False
        )
        data = ProductionSessionCreate(
            track_id=1, chunk_id=10, task_type="translate", prompt_text="Translate this",
        )

        await service.record_production(data)

        call_kwargs = service._repo.create_session.call_args[1]
        assert call_kwargs["feeds_srs"] is False
        service._chunk_service.apply_production_review.assert_not_called()


class TestRecordSession:
    async def test_conversation_does_not_feed_srs(self, service):
        service._repo.create_session.return_value = _make_session_orm(
            session_type="conversation", feeds_srs=False
        )
        data = SessionCreate(track_id=1, session_type="conversation")

        await service.record_session(data)

        call_kwargs = service._repo.create_session.call_args[1]
        assert call_kwargs["feeds_srs"] is False
        service._chunk_service.apply_srs_review.assert_not_called()

    async def test_correction_does_not_feed_srs_without_score(self, service):
        service._repo.create_session.return_value = _make_session_orm(
            session_type="correction", feeds_srs=False
        )
        data = SessionCreate(track_id=1, chunk_id=5, session_type="correction")

        await service.record_session(data)

        service._chunk_service.apply_srs_review.assert_not_called()


class TestGetDailyProgress:
    async def test_returns_progress_per_active_track(self, service):
        service._track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr", daily_quota=10),
        ]
        service._repo.count_srs_reviews_today.return_value = 7

        result = await service.get_daily_progress()

        assert len(result) == 1
        assert result[0].track_code == "fr"
        assert result[0].completed_today == 7
        assert result[0].daily_quota == 10
        assert result[0].quota_met is False

    async def test_quota_met_when_completed_equals_quota(self, service):
        service._track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr", daily_quota=10),
        ]
        service._repo.count_srs_reviews_today.return_value = 10

        result = await service.get_daily_progress()
        assert result[0].quota_met is True

    async def test_filters_by_track_id(self, service):
        service._track_repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr"),
            _make_track_orm(id=2, code="ru"),
        ]
        service._repo.count_srs_reviews_today.return_value = 5

        result = await service.get_daily_progress(track_id=1)

        assert len(result) == 1
        assert result[0].track_id == 1
