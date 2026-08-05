import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from unittest.mock import AsyncMock, call

from app.assistant.commands.handlers.cs import handle_cs, _WM_KEY
from app.features.core.working_memory.schemas import WorkingMemoryRead
from app.features.cs.stats.schemas import StatsSummary
from app.features.cs.study_plans.schemas import StudyPlanItemRead, StudyPlanRead


def _make_summary(**overrides) -> StatsSummary:
    defaults = dict(
        current_streak=1,
        longest_streak=3,
        total_solved=10,
        total_attempted=15,
        by_difficulty=[],
        by_tag=[],
        by_language=[],
        by_day=[],
        weakest_tags=[],
        untried_tags=[],
    )
    defaults.update(overrides)
    return StatsSummary(**defaults)


@pytest.fixture
def mock_stats_service():
    svc = AsyncMock()
    svc.get_summary = AsyncMock(return_value=_make_summary())
    return svc


@pytest.fixture
def mock_working_memory_service():
    svc = AsyncMock()
    svc.upsert = AsyncMock(return_value=WorkingMemoryRead(
        id=1, key=_WM_KEY, value="10 solved, current streak 1d (longest 3d)",
        importance=0.7, expires_at=datetime.now(timezone.utc), session_id=None,
        created_at=datetime.now(timezone.utc),
    ))
    return svc


class TestHandleCs:
    async def test_upserts_working_memory_with_summary(self, mock_stats_service, mock_working_memory_service):
        result = await handle_cs("context", {}, mock_stats_service, mock_working_memory_service)

        mock_working_memory_service.upsert.assert_awaited_once()
        call_arg = mock_working_memory_service.upsert.call_args[0][0]
        assert call_arg.key == _WM_KEY
        assert "10 solved" in call_arg.value
        assert "no activity in the last 7d" in call_arg.value
        assert call_arg.expires_at is not None
        assert result["wm_id"] == 1

    async def test_raises_on_unknown_command(self, mock_stats_service, mock_working_memory_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_cs("list", {}, mock_stats_service, mock_working_memory_service)
        assert exc_info.value.status_code == 400

    async def test_includes_active_plan_pending_items(self, mock_stats_service, mock_working_memory_service):
        plan = StudyPlanRead(
            id=1, cadence="weekly", period_start=datetime.now(timezone.utc).date(), status="active",
            rationale=None,
            items=[StudyPlanItemRead(
                id=1, item_type="problem", description="do DP problem", problem_id=None,
                url=None, is_done=False, completed_at=None, position=0,
            )],
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        mock_study_plan_service = AsyncMock()
        mock_study_plan_service.get_active_plan = AsyncMock(return_value=plan)

        await handle_cs(
            "context", {}, mock_stats_service, mock_working_memory_service,
            study_plan_service=mock_study_plan_service,
        )

        mock_study_plan_service.get_active_plan.assert_awaited_once_with("weekly")
        call_arg = mock_working_memory_service.upsert.call_args[0][0]
        assert "weekly plan pending: do DP problem" in call_arg.value

    async def test_falls_back_to_monthly_plan_when_no_weekly(self, mock_stats_service, mock_working_memory_service):
        mock_study_plan_service = AsyncMock()
        mock_study_plan_service.get_active_plan = AsyncMock(return_value=None)

        await handle_cs(
            "context", {}, mock_stats_service, mock_working_memory_service,
            study_plan_service=mock_study_plan_service,
        )

        assert mock_study_plan_service.get_active_plan.await_args_list == [
            call("weekly"), call("monthly"),
        ]
