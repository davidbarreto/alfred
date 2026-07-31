from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.cs.study_plans.schemas import StudyPlanCreate, StudyPlanItemCreate
from app.features.cs.study_plans.service import StudyPlanService


def _make_plan_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.cadence = kwargs.get("cadence", "weekly")
    orm.period_start = kwargs.get("period_start", date(2026, 7, 31))
    orm.status = kwargs.get("status", "active")
    orm.rationale = kwargs.get("rationale", "focus on dp")
    orm.items = kwargs.get("items", [])
    orm.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    orm.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return orm


@pytest.fixture
def service():
    svc = StudyPlanService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestCreatePlan:
    async def test_delegates_to_repo(self, service):
        service._repo.create_plan.return_value = _make_plan_orm()
        data = StudyPlanCreate(cadence="weekly", period_start=date(2026, 7, 31), items=[
            StudyPlanItemCreate(item_type="topic_review", description="review dp"),
        ])
        result = await service.create_plan(data)
        service._repo.create_plan.assert_called_once_with(data)
        assert result.cadence == "weekly"


class TestMarkItemDone:
    async def test_returns_true_when_found(self, service):
        service._repo.mark_item_done.return_value = MagicMock()
        result = await service.mark_item_done(1)
        assert result is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.mark_item_done.return_value = None
        result = await service.mark_item_done(999)
        assert result is False


class TestAutoCompleteItemsForProblem:
    async def test_calls_repo_with_problem_id(self, service):
        service._repo.auto_complete_items_for_problem.return_value = 2
        await service.auto_complete_items_for_problem(42)
        service._repo.auto_complete_items_for_problem.assert_called_once_with(42)

    async def test_does_not_raise_when_zero_completed(self, service):
        service._repo.auto_complete_items_for_problem.return_value = 0
        await service.auto_complete_items_for_problem(42)
