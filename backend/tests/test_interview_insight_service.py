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


def _make_stage(stage_type: str, status: str, scheduled_at=None):
    stage = MagicMock()
    stage.stage_type = stage_type
    stage.status = status
    stage.scheduled_at = scheduled_at
    return stage


def _make_company(name: str):
    company = MagicMock()
    company.name = name
    return company


def _make_preferences_orm(**kwargs):
    orm = MagicMock()
    orm.work_regimes = kwargs.get("work_regimes", [])
    orm.target_office_days_per_month = kwargs.get("target_office_days_per_month", None)
    orm.salary_min = kwargs.get("salary_min", None)
    orm.salary_max = kwargs.get("salary_max", None)
    orm.salary_currency = kwargs.get("salary_currency", None)
    orm.locations = kwargs.get("locations", [])
    orm.tech_stack = kwargs.get("tech_stack", [])
    orm.roles = kwargs.get("roles", [])
    orm.career_objectives = kwargs.get("career_objectives", None)
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
    svc._preferences_repo = AsyncMock()
    svc._preferences_repo.get_preferences.return_value = _make_preferences_orm()
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

    async def test_prompt_includes_todays_date(self, service):
        svc, llm_provider = service
        svc._process_repo.get_active_processes.return_value = []
        llm_provider.complete.return_value = LlmResponse(
            text='{"content": "x", "focus_process_ids": []}', tokens_input=1, tokens_output=1, finish_reason="STOP",
        )
        svc._repo.create_insight.return_value = _make_insight_orm(process_ids=[])

        with patch("app.features.organizer.interviews.insights.service.create_llm_call", new=AsyncMock()):
            await svc.generate_insights()

        _, kwargs = llm_provider.complete.call_args
        assert "Today's date is" in kwargs["system"]

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


class TestBuildProcessSummary:
    """Regression test: the LLM once judged a stage on 2026-09-11 as "closer" than one on
    2026-09-04, seemingly because the prompt made it do its own date comparison across an
    unsorted, unlabeled list. The summary is now precomputed and sorted server-side so the
    model doesn't have to do date arithmetic itself."""

    async def test_orders_by_soonest_next_stage_not_priority_or_id(self, service):
        svc, _ = service
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)

        teya = _make_process_orm(id=1, company_id=10, role_title="Senior Backend Engineer")
        teya.priority = "high"
        teya.stages = [_make_stage("behavioral", "scheduled", datetime(2026, 9, 11, 17, 0, tzinfo=timezone.utc))]

        squarespace = _make_process_orm(id=2, company_id=20, role_title="Staff Software Engineer")
        squarespace.priority = "medium"
        squarespace.stages = [_make_stage("code_review", "scheduled", datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc))]

        svc._process_repo.get_active_processes.return_value = [teya, squarespace]
        companies = {10: _make_company("Teya"), 20: _make_company("Squarespace")}
        svc._company_repo.get_company.side_effect = lambda cid: companies[cid]

        summary, ids = await svc._build_process_summary(now)

        assert ids == [2, 1]
        assert summary.index("Process id 2") < summary.index("Process id 1")
        assert "NEXT: code_review in 1 day(s)" in summary
        assert "NEXT: behavioral in 8 day(s)" in summary

    async def test_process_with_no_scheduled_stage_sorts_last(self, service):
        svc, _ = service
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)

        no_stage = _make_process_orm(id=1, company_id=10)
        no_stage.stages = []
        has_stage = _make_process_orm(id=2, company_id=20)
        has_stage.stages = [_make_stage("phone_screen", "scheduled", datetime(2026, 9, 5, tzinfo=timezone.utc))]

        svc._process_repo.get_active_processes.return_value = [no_stage, has_stage]
        svc._company_repo.get_company.return_value = _make_company("Acme")

        summary, ids = await svc._build_process_summary(now)

        assert ids == [2, 1]
        assert "NEXT: nothing scheduled" in summary


class TestBuildPreferencesSummary:
    def test_returns_placeholder_when_nothing_configured(self):
        summary = InterviewInsightService._build_preferences_summary(_make_preferences_orm())
        assert summary == "No preferences configured."

    def test_includes_configured_fields(self):
        preferences = _make_preferences_orm(
            work_regimes=["remote", "hybrid"],
            target_office_days_per_month=4.0,
            salary_min=80000,
            salary_max=100000,
            salary_currency="EUR",
            locations=["Lisbon"],
            tech_stack=["Java", "Python"],
            roles=["Backend Engineer"],
            career_objectives="Move into a staff-level role",
        )
        summary = InterviewInsightService._build_preferences_summary(preferences)
        assert "work regime: remote, hybrid" in summary
        assert "target office days/month: 4.0" in summary
        assert "salary expectations: 80000-100000 EUR" in summary
        assert "preferred locations: Lisbon" in summary
        assert "preferred tech stack: Java, Python" in summary
        assert "target roles: Backend Engineer" in summary
        assert "career objectives: Move into a staff-level role" in summary


class TestGenerateInsightsWithPreferences:
    async def test_prompt_includes_preferences_summary(self, service):
        svc, llm_provider = service
        svc._process_repo.get_active_processes.return_value = []
        svc._preferences_repo.get_preferences.return_value = _make_preferences_orm(
            work_regimes=["remote"], roles=["Backend Engineer"]
        )
        llm_provider.complete.return_value = LlmResponse(
            text='{"content": "x", "focus_process_ids": []}', tokens_input=1, tokens_output=1, finish_reason="STOP",
        )
        svc._repo.create_insight.return_value = _make_insight_orm(process_ids=[])

        with patch("app.features.organizer.interviews.insights.service.create_llm_call", new=AsyncMock()):
            await svc.generate_insights()

        _, kwargs = llm_provider.complete.call_args
        assert "work regime: remote" in kwargs["system"]
        assert "target roles: Backend Engineer" in kwargs["system"]


class TestGetInsightsHistory:
    async def test_returns_insights_from_repo(self, service):
        svc, _ = service
        svc._repo.get_insights.return_value = [_make_insight_orm(id=1), _make_insight_orm(id=2)]
        filters = InterviewInsightFilters(limit=20, offset=0)
        result = await svc.get_insights_history(filters)
        svc._repo.get_insights.assert_called_once_with(filters)
        assert [i.id for i in result] == [1, 2]
