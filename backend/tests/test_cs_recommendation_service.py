from unittest.mock import AsyncMock

import pytest

from app.features.cs.recommendations.service import RecommendationService
from app.features.cs.stats.schemas import CandidateProblem, StatsSummary, TagBreakdown


def _summary(weakest_tags=None, by_tag=None, untried_tags=None, total_solved=10):
    return StatsSummary(
        current_streak=1,
        longest_streak=2,
        total_solved=total_solved,
        total_attempted=total_solved,
        by_difficulty=[],
        by_tag=by_tag or [],
        by_language=[],
        by_day=[],
        weakest_tags=weakest_tags or [],
        untried_tags=untried_tags or [],
    )


def _tag_breakdown(tag, attempted, solved, submissions=None):
    submissions = attempted if submissions is None else submissions
    return TagBreakdown(
        tag=tag,
        attempted=attempted,
        solved=solved,
        solve_rate=solved / attempted,
        submissions=submissions,
        avg_attempts_per_solve=submissions / solved if solved else None,
    )


def _candidate(external_id="1A", id=1):
    return CandidateProblem(
        id=id, platform_id=1, external_id=external_id, name="Problem", url=None,
        difficulty="easy", tags=["dp"],
    )


@pytest.fixture
def service():
    svc = RecommendationService(session=AsyncMock())
    svc._stats = AsyncMock()
    return svc


class TestGetLiveRecommendation:
    async def test_returns_none_when_no_submissions_at_all(self, service):
        service._stats.get_summary.return_value = _summary(weakest_tags=[], total_solved=0)
        result = await service.get_live_recommendation()
        assert result is None

    async def test_returns_untried_tag_suggestion_when_no_weak_tags_but_history_exists(self, service):
        service._stats.get_summary.return_value = _summary(weakest_tags=[], untried_tags=["graphs"])
        service._stats.get_candidate_problems.return_value = [_candidate()]
        result = await service.get_live_recommendation()
        assert result.tag == "graphs"
        assert result.solve_rate is None
        assert len(result.candidates) == 1

    async def test_returns_generic_strong_performance_message_when_all_tags_tried(self, service):
        service._stats.get_summary.return_value = _summary(weakest_tags=[], untried_tags=[])
        result = await service.get_live_recommendation()
        assert result.tag is None
        assert result.candidates == []

    async def test_returns_recommendation_for_weakest_tag(self, service):
        weak = _tag_breakdown("dp", attempted=5, solved=1)
        service._stats.get_summary.return_value = _summary(weakest_tags=[weak])
        service._stats.get_candidate_problems.return_value = [_candidate()]
        result = await service.get_live_recommendation()
        assert result.tag == "dp"
        assert result.solve_rate == 0.2
        assert len(result.candidates) == 1
