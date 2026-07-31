from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.cs.platforms.schemas import PlatformCreate, PlatformFilters, PlatformUpdate
from app.features.cs.platforms.service import PlatformService


def _make_platform_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.code = kwargs.get("code", "codeforces")
    orm.handle = kwargs.get("handle", "tourist")
    orm.sync_enabled = kwargs.get("sync_enabled", True)
    orm.last_synced_at = kwargs.get("last_synced_at", None)
    orm.last_submission_external_id = kwargs.get("last_submission_external_id", None)
    orm.rating = kwargs.get("rating", None)
    orm.max_rating = kwargs.get("max_rating", None)
    orm.rank = kwargs.get("rank", None)
    orm.created_at = kwargs.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    orm.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return orm


@pytest.fixture
def service():
    svc = PlatformService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestGetPlatformByCode:
    async def test_returns_platform_read_when_found(self, service):
        service._repo.get_platform_by_code.return_value = _make_platform_orm(code="leetcode")
        result = await service.get_platform_by_code("leetcode")
        assert result.code == "leetcode"

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_platform_by_code.return_value = None
        result = await service.get_platform_by_code("hackerrank")
        assert result is None


class TestCreatePlatform:
    async def test_creates_and_returns_read(self, service):
        service._repo.create_platform.return_value = _make_platform_orm(code="codeforces")
        result = await service.create_platform(PlatformCreate(code="codeforces", handle="tourist"))
        assert result.code == "codeforces"


class TestUpdatePlatform:
    async def test_updates_watermark_fields(self, service):
        service._repo.update_platform.return_value = _make_platform_orm(
            last_submission_external_id="12345", rating=2600
        )
        result = await service.update_platform(
            1, PlatformUpdate(last_submission_external_id="12345", rating=2600)
        )
        assert result.last_submission_external_id == "12345"
        assert result.rating == 2600

    async def test_returns_none_when_not_found(self, service):
        service._repo.update_platform.return_value = None
        result = await service.update_platform(999, PlatformUpdate(rating=1))
        assert result is None


class TestGetPlatforms:
    async def test_returns_list(self, service):
        service._repo.get_platforms.return_value = [
            _make_platform_orm(id=1, code="codeforces"),
            _make_platform_orm(id=2, code="leetcode"),
        ]
        result = await service.get_platforms(PlatformFilters())
        assert [p.code for p in result] == ["codeforces", "leetcode"]
