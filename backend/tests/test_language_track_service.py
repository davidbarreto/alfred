import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from app.features.language.tracks.service import TrackService
from app.features.language.tracks.schemas import TrackCreate, TrackRead, TrackUpdate, TrackFilters


def _make_track_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.code = kwargs.get("code", "fr")
    orm.name = kwargs.get("name", "French")
    orm.level = kwargs.get("level", "B1")
    orm.daily_quota = kwargs.get("daily_quota", 10)
    orm.review_mode = kwargs.get("review_mode", "balanced")
    orm.active = kwargs.get("active", True)
    orm.created_at = kwargs.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    orm.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return orm


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    svc = TrackService(session=mock_session)
    svc._repo = AsyncMock()
    return svc


class TestGetTrack:
    async def test_returns_track_read_when_found(self, service):
        service._repo.get_track.return_value = _make_track_orm()
        result = await service.get_track(1)
        assert result is not None
        assert result.id == 1
        assert result.code == "fr"

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_track.return_value = None
        result = await service.get_track(999)
        assert result is None


class TestGetTracks:
    async def test_returns_list_of_track_reads(self, service):
        service._repo.get_tracks.return_value = [
            _make_track_orm(id=1, code="fr"),
            _make_track_orm(id=2, code="ru"),
        ]
        filters = TrackFilters(active_only=True)
        result = await service.get_tracks(filters)
        assert len(result) == 2
        assert result[0].code == "fr"
        assert result[1].code == "ru"

    async def test_returns_empty_list_when_no_tracks(self, service):
        service._repo.get_tracks.return_value = []
        result = await service.get_tracks(TrackFilters())
        assert result == []


class TestCreateTrack:
    async def test_creates_and_returns_track_read(self, service):
        data = TrackCreate(code="fr", name="French", level="B1")
        service._repo.create_track.return_value = _make_track_orm(code="fr", name="French")
        result = await service.create_track(data)
        service._repo.create_track.assert_called_once_with(data)
        assert result.code == "fr"

    async def test_passes_all_fields_to_repo(self, service):
        data = TrackCreate(code="ru", name="Russian", level="A2", daily_quota=15, review_mode="shadowing_heavy")
        service._repo.create_track.return_value = _make_track_orm(code="ru", daily_quota=15)
        await service.create_track(data)
        service._repo.create_track.assert_called_once_with(data)


class TestUpdateTrack:
    async def test_returns_updated_track(self, service):
        service._repo.update_track.return_value = _make_track_orm(daily_quota=20)
        result = await service.update_track(1, TrackUpdate(daily_quota=20))
        assert result is not None
        assert result.daily_quota == 20

    async def test_returns_none_when_not_found(self, service):
        service._repo.update_track.return_value = None
        result = await service.update_track(999, TrackUpdate(active=False))
        assert result is None


class TestDeleteTrack:
    async def test_delegates_to_repo(self, service):
        await service.delete_track(1)
        service._repo.delete_track.assert_called_once_with(1)
