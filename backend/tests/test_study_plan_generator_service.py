import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.cs.stats.schemas import CandidateProblem, StatsSummary, TagBreakdown
from app.features.study.generator.service import (
    PlanGenerationError,
    StudyPlanGeneratorService,
    StudyTrackNotFoundError,
)
from app.shared.llm import LlmResponse

_NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
_PATCH_LLM_LOG = "app.features.study.generator.service.create_llm_call"


def _summary(weakest_tags=None, by_tag=None):
    return StatsSummary(
        current_streak=1, longest_streak=2, total_solved=10, total_attempted=10,
        by_difficulty=[], by_tag=by_tag or [], by_language=[], by_day=[],
        weakest_tags=weakest_tags or [], untried_tags=[],
    )


def _tag_breakdown(tag, attempted, solved):
    return TagBreakdown(
        tag=tag, attempted=attempted, solved=solved, solve_rate=solved / attempted,
        submissions=attempted, avg_attempts_per_solve=1.0 if solved else None,
    )


def _candidate(external_id="1A", url="https://codeforces.com/problemset/problem/1/A"):
    return CandidateProblem(
        id=1, platform_id=1, external_id=external_id, name="Problem", url=url, difficulty="easy", tags=["dp"],
    )


def _llm_json(**overrides) -> LlmResponse:
    payload = {
        "title": "Dynamic programming",
        "goal": "Solve medium DP problems without hints",
        "priority": "high",
        "tags": ["Algorithms", "dynamic-programming"],
        "items": [{"description": "Review DP basics"}],
    }
    payload.update(overrides)
    return LlmResponse(text=json.dumps(payload), tokens_input=1, tokens_output=1)


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def service(mock_llm):
    svc = StudyPlanGeneratorService(llm_provider=mock_llm, session=AsyncMock())
    svc._stats = AsyncMock()
    svc._stats.get_summary.return_value = _summary(weakest_tags=[_tag_breakdown("dp", 5, 1)])
    svc._stats.get_candidate_problems.return_value = [_candidate()]
    svc._tracks = AsyncMock()
    svc._tracks.get_track_by_name.return_value = MagicMock(id=7)
    svc._plans = AsyncMock()
    svc._plans.get_tag_names.return_value = ["algorithms"]
    svc._plans.create_plan.return_value = MagicMock(id=1, status="active")
    return svc


async def _generate(service):
    with patch(_PATCH_LLM_LOG, new_callable=AsyncMock):
        await service.generate_from_cs_stats()
    return service._plans.create_plan.call_args[0][0]


class TestGenerateFromCsStats:
    async def test_creates_plan_in_software_engineering_track(self, service, mock_llm):
        mock_llm.complete.return_value = _llm_json()

        data = await _generate(service)

        assert data.track_id == 7
        assert data.title == "Dynamic programming"
        assert data.goal == "Solve medium DP problems without hints"
        assert data.priority == "high"

    async def test_normalises_tags(self, service, mock_llm):
        mock_llm.complete.return_value = _llm_json(tags=["Algorithms", "algorithms", " DP ", "graphs", "extra"])

        data = await _generate(service)

        assert data.tags == ["algorithms", "dp", "graphs"]

    async def test_sends_existing_tags_to_llm(self, service, mock_llm):
        mock_llm.complete.return_value = _llm_json()

        await _generate(service)

        context = mock_llm.complete.call_args[0][0][0]["content"]
        assert "Existing study tags: algorithms" in context

    async def test_problem_item_uses_candidate_url(self, service, mock_llm):
        mock_llm.complete.return_value = _llm_json(items=[
            {"description": "Solve Problem", "candidate_external_id": "1A", "url": "https://invented.example"},
        ])

        data = await _generate(service)

        assert data.items[0].url == "https://codeforces.com/problemset/problem/1/A"
        assert data.items[0].source_type == "cs_tag"

    async def test_skips_item_with_unknown_candidate(self, service, mock_llm):
        mock_llm.complete.return_value = _llm_json(items=[
            {"description": "Solve it", "candidate_external_id": "UNKNOWN"},
            {"description": "Review DP basics"},
        ])

        data = await _generate(service)

        assert [item.description for item in data.items] == ["Review DP basics"]
        assert data.items[0].position == 0

    async def test_unknown_priority_falls_back_to_medium(self, service, mock_llm):
        mock_llm.complete.return_value = _llm_json(priority="urgent")

        data = await _generate(service)

        assert data.priority == "medium"

    async def test_strips_markdown_fences(self, service, mock_llm):
        mock_llm.complete.return_value = LlmResponse(
            text="```json\n" + _llm_json().text + "\n```", tokens_input=1, tokens_output=1,
        )

        data = await _generate(service)

        assert data.title == "Dynamic programming"

    async def test_falls_back_to_least_practiced_tags_when_no_weak_tag_qualifies(self, service, mock_llm):
        # Rank by fewest attempts (not alphabetically) so the fallback reflects genuine gaps in evidence.
        service._stats.get_summary.return_value = _summary(
            by_tag=[_tag_breakdown("binary search", 10, 9), _tag_breakdown("zigzag", 2, 1)]
        )
        mock_llm.complete.return_value = _llm_json()

        await _generate(service)

        assert service._stats.get_candidate_problems.call_args[0][0] == ["zigzag", "binary search"]

    async def test_raises_on_invalid_json(self, service, mock_llm):
        mock_llm.complete.return_value = LlmResponse(text="not json", tokens_input=1, tokens_output=1)

        with patch(_PATCH_LLM_LOG, new_callable=AsyncMock), pytest.raises(PlanGenerationError):
            await service.generate_from_cs_stats()
        service._plans.create_plan.assert_not_awaited()

    @pytest.mark.parametrize("overrides", [{"title": ""}, {"goal": ""}, {"items": []}])
    async def test_raises_on_incomplete_plan(self, service, mock_llm, overrides):
        mock_llm.complete.return_value = _llm_json(**overrides)

        with patch(_PATCH_LLM_LOG, new_callable=AsyncMock), pytest.raises(PlanGenerationError):
            await service.generate_from_cs_stats()
        service._plans.create_plan.assert_not_awaited()

    async def test_raises_when_track_missing(self, service, mock_llm):
        service._tracks.get_track_by_name.return_value = None

        with pytest.raises(StudyTrackNotFoundError):
            await service.generate_from_cs_stats()
        mock_llm.complete.assert_not_called()
