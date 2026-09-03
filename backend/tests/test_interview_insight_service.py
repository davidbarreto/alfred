from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.organizer.interviews.insights.schemas import InterviewInsightFilters
from app.features.organizer.interviews.insights.service import InterviewInsightService
from app.shared.llm import LlmResponse


def _make_process_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.company_id = kwargs.get("company_id", 1)
    orm.role_title = kwargs.get("role_title", "Backend Engineer")
    orm.priority = None
    orm.study_plan_id = None
    orm.stages = []
    return orm


def _make_insight_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.content = kwargs.get("content", "Focus on X")
    orm.model = kwargs.get("model", "gemini-test")
    orm.process_ids = kwargs.get("process_ids", [1])
    orm.generated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    orm.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return orm


@pytest.fixture
def service():
    llm_provider = MagicMock()
    llm_provider.provider = "google"
    llm_provider.model = "gemini-test"
    llm_provider.complete = AsyncMock()
    svc = InterviewInsightService(session=AsyncMock(), llm_provider=llm_provider)
    svc._repo = AsyncMock()
    svc._process_repo = AsyncMock()
    svc._company_repo = AsyncMock()
    return svc, llm_provider


class TestGenerateInsights:
    async def test_only_considers_active_processes(self, service):
        svc, llm_provider = service
        svc._process_repo.get_active_processes.return_value = [_make_process_orm(id=1)]
        svc._company_repo.get_company.return_value = MagicMock(name="Acme")
        llm_provider.complete.return_value = LlmResponse(
            text='{"content": "Focus on X", "focus_process_ids": [1]}',
            tokens_input=50, tokens_output=20, finish_reason="STOP",
        )
        svc._repo.create_insight.return_value = _make_insight_orm()

        with patch("app.features.organizer.interviews.insights.service.create_llm_call", new=AsyncMock()):
            result = await svc.generate_insights()

        svc._process_repo.get_active_processes.assert_called_once()
        svc._repo.create_insight.assert_called_once()
        _, kwargs = svc._repo.create_insight.call_args
        assert kwargs["process_ids"] == [1]
        assert kwargs["content"] == "Focus on X"
        assert result.content == "Focus on X"

    async def test_logs_llm_call_with_correct_feature(self, service):
        svc, llm_provider = service
        svc._process_repo.get_active_processes.return_value = []
        llm_provider.complete.return_value = LlmResponse(
            text='{"content": "No active processes", "focus_process_ids": []}',
            tokens_input=10, tokens_output=5, finish_reason="STOP",
        )
        svc._repo.create_insight.return_value = _make_insight_orm(process_ids=[])

        with patch("app.features.organizer.interviews.insights.service.create_llm_call", new=AsyncMock()) as mock_log:
            await svc.generate_insights()

        assert mock_log.call_args.kwargs["feature"] == "interview_insights"


class TestGetInsightsHistory:
    async def test_returns_insights_from_repo(self, service):
        svc, _ = service
        svc._repo.get_insights.return_value = [_make_insight_orm(id=1), _make_insight_orm(id=2)]
        filters = InterviewInsightFilters(limit=20, offset=0)
        result = await svc.get_insights_history(filters)
        svc._repo.get_insights.assert_called_once_with(filters)
        assert [i.id for i in result] == [1, 2]
