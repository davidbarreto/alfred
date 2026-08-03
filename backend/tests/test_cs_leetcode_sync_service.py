from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.cs.platforms.leetcode_sync_service import LeetCodeSyncService


def _platform_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.code = "leetcode"
    orm.sync_enabled = kwargs.get("sync_enabled", True)
    return orm


def _problem_orm(id, external_id):
    obj = MagicMock()
    obj.id = id
    obj.external_id = external_id
    return obj


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def service(mock_session, mock_client):
    svc = LeetCodeSyncService(session=mock_session, client=mock_client)
    svc._platforms = AsyncMock()
    svc._problems = AsyncMock()
    svc._submissions = AsyncMock()
    svc._plans = AsyncMock()
    return svc


class TestRefreshMetrics:
    async def test_skips_when_platform_not_configured(self, service):
        service._platforms.get_platform_by_code.return_value = None
        result = await service.refresh_metrics()
        assert result == 0

    async def test_updates_each_problem_from_question_data(self, service, mock_client):
        service._platforms.get_platform_by_code.return_value = _platform_orm()
        service._problems.get_problems_by_platform.return_value = [
            _problem_orm(1, "two-sum"),
            _problem_orm(2, "add-two-numbers"),
        ]
        mock_client.get_question_data.return_value = {"acRate": 55.5, "likes": 100, "dislikes": 2}

        with patch("app.features.cs.platforms.leetcode_sync_service.asyncio.sleep", new_callable=AsyncMock):
            updated = await service.refresh_metrics()

        assert updated == 2
        assert service._problems.update_problem.call_count == 2
        service._platforms.update_platform.assert_called_once()
