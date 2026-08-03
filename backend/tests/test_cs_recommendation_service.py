import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.cs.recommendations.service import RecommendationService
from app.features.cs.stats.schemas import CandidateProblem, StatsSummary, TagBreakdown
from app.features.cs.study_plans.schemas import StudyPlanRead
from app.shared.llm import LlmResponse


def _summary(weakest_tags=None, by_tag=None, untried_tags=None, total_solved=10):
    return StatsSummary(
        current_streak=1,
        longest_streak=2,
        total_solved=total_solved,
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


def _plan_orm():
    orm = MagicMock()
    orm.id = 1
    orm.cadence = "weekly"
    orm.period_start = None
    orm.status = "active"
    orm.rationale = "focus on dp"
    orm.items = []
    orm.created_at = None
    orm.updated_at = None
    return orm


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def service(mock_llm, mock_session):
    svc = RecommendationService(llm_provider=mock_llm, session=mock_session)
    svc._stats = AsyncMock()
    svc._plans = AsyncMock()
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


class TestGeneratePlan:
    async def test_skips_problem_item_with_unknown_candidate_id(self, service, mock_llm):
        weak = _tag_breakdown("dp", attempted=5, solved=1)
        service._stats.get_summary.return_value = _summary(weakest_tags=[weak])
        service._stats.get_candidate_problems.return_value = [_candidate(external_id="1A", id=1)]
        mock_llm.complete.return_value = LlmResponse(
            text=json.dumps({
                "rationale": "focus on dp",
                "items": [
                    {"item_type": "problem", "description": "solve it", "candidate_external_id": "UNKNOWN"},
                    {"item_type": "topic_review", "description": "review dp basics"},
                ],
            }),
            tokens_input=10, tokens_output=10,
        )
        service._plans.create_plan.return_value = _plan_orm()

        with patch("app.features.cs.recommendations.service.create_llm_call", new_callable=AsyncMock):
            await service.generate_plan("weekly")

        created_data = service._plans.create_plan.call_args[0][0]
        assert len(created_data.items) == 1
        assert created_data.items[0].item_type == "topic_review"

    async def test_resolves_problem_id_for_known_candidate(self, service, mock_llm):
        weak = _tag_breakdown("dp", attempted=5, solved=1)
        service._stats.get_summary.return_value = _summary(weakest_tags=[weak])
        service._stats.get_candidate_problems.return_value = [_candidate(external_id="1A", id=42)]
        mock_llm.complete.return_value = LlmResponse(
            text=json.dumps({
                "rationale": "focus on dp",
                "items": [
                    {"item_type": "problem", "description": "solve it", "candidate_external_id": "1A"},
                ],
            }),
            tokens_input=10, tokens_output=10,
        )
        service._plans.create_plan.return_value = _plan_orm()

        with patch("app.features.cs.recommendations.service.create_llm_call", new_callable=AsyncMock):
            await service.generate_plan("weekly")

        created_data = service._plans.create_plan.call_args[0][0]
        assert created_data.items[0].problem_id == 42

    async def test_raises_on_invalid_json(self, service, mock_llm):
        service._stats.get_summary.return_value = _summary(weakest_tags=[])
        service._stats.get_candidate_problems.return_value = []
        mock_llm.complete.return_value = LlmResponse(text="not json", tokens_input=1, tokens_output=1)

        with patch("app.features.cs.recommendations.service.create_llm_call", new_callable=AsyncMock):
            with pytest.raises(ValueError):
                await service.generate_plan("weekly")

    async def test_strips_markdown_fences_before_parsing(self, service, mock_llm):
        service._stats.get_summary.return_value = _summary(weakest_tags=[])
        service._stats.get_candidate_problems.return_value = []
        mock_llm.complete.return_value = LlmResponse(
            text="```json\n" + json.dumps({"rationale": "r", "items": []}) + "\n```",
            tokens_input=1, tokens_output=1,
        )
        service._plans.create_plan.return_value = _plan_orm()

        with patch("app.features.cs.recommendations.service.create_llm_call", new_callable=AsyncMock):
            await service.generate_plan("weekly")

        created_data = service._plans.create_plan.call_args[0][0]
        assert created_data.rationale == "r"
