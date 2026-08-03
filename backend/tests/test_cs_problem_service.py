from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.cs.problems.schemas import AttemptedProblemFilters, ProblemCreate, ProblemFilters
from app.features.cs.problems.service import ProblemService


def _make_tag(name):
    tag = MagicMock()
    tag.id = 1
    tag.name = name
    return tag


def _make_problem_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.platform_id = kwargs.get("platform_id", 1)
    orm.external_id = kwargs.get("external_id", "100A")
    orm.name = kwargs.get("name", "Test Problem")
    orm.url = kwargs.get("url", None)
    orm.difficulty_raw = kwargs.get("difficulty_raw", "1200")
    orm.difficulty = kwargs.get("difficulty", "medium")
    orm.tags_raw = kwargs.get("tags_raw", ["dp"])
    orm.tags = kwargs.get("tags", [_make_tag("dynamic programming")])
    orm.acceptance_rate = kwargs.get("acceptance_rate", None)
    orm.solved_count = kwargs.get("solved_count", None)
    orm.likes = kwargs.get("likes", None)
    orm.dislikes = kwargs.get("dislikes", None)
    orm.metrics_updated_at = kwargs.get("metrics_updated_at", None)
    orm.created_at = kwargs.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    orm.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return orm


@pytest.fixture
def service():
    svc = ProblemService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestGetProblem:
    async def test_returns_problem_with_tags(self, service):
        service._repo.get_problem.return_value = _make_problem_orm()
        result = await service.get_problem(1)
        assert result.external_id == "100A"
        assert result.tags[0].name == "dynamic programming"

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_problem.return_value = None
        result = await service.get_problem(999)
        assert result is None


class TestGetProblems:
    async def test_returns_list(self, service):
        service._repo.get_problems.return_value = [_make_problem_orm(id=1), _make_problem_orm(id=2)]
        result = await service.get_problems(ProblemFilters())
        assert len(result) == 2


class TestGetAttemptedProblems:
    async def test_maps_attempts_and_solved_onto_problem(self, service):
        last_attempted = datetime(2026, 8, 1, tzinfo=timezone.utc)
        service._repo.get_attempted_problems.return_value = [
            (_make_problem_orm(id=1), 3, True, last_attempted),
        ]
        result = await service.get_attempted_problems(AttemptedProblemFilters())
        assert len(result) == 1
        assert result[0].attempts == 3
        assert result[0].solved is True
        assert result[0].last_attempted_at == last_attempted


class TestGetProblemsByPlatform:
    async def test_returns_list(self, service):
        service._repo.get_problems_by_platform.return_value = [_make_problem_orm(id=1), _make_problem_orm(id=2)]
        result = await service.get_problems_by_platform(1)
        assert len(result) == 2


class TestUpsertProblem:
    async def test_delegates_to_repo(self, service):
        service._repo.upsert_problem.return_value = _make_problem_orm(external_id="200B")
        data = ProblemCreate(platform_id=1, external_id="200B", name="Other", tags=["dp"])
        result = await service.upsert_problem(data)
        service._repo.upsert_problem.assert_called_once_with(data)
        assert result.external_id == "200B"
