from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.cs.study_plans.schemas import StudyPlanCreate, StudyPlanFilters, StudyPlanItemCreate
from app.features.cs.study_plans.service import ActivePlanIncompleteError, StudyPlanService


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


def _make_item_orm(is_done: bool):
    item = MagicMock()
    item.id = 1
    item.item_type = "problem"
    item.description = "x"
    item.problem_id = None
    item.url = None
    item.is_done = is_done
    item.completed_at = None
    item.position = 0
    return item


@pytest.fixture
def service():
    svc = StudyPlanService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestCreatePlan:
    async def test_delegates_to_repo_when_no_active_plan(self, service):
        service._repo.get_active_plan.return_value = None
        service._repo.create_plan.return_value = _make_plan_orm()
        data = StudyPlanCreate(cadence="weekly", period_start=date(2026, 7, 31), items=[
            StudyPlanItemCreate(item_type="topic_review", description="review dp"),
        ])
        result = await service.create_plan(data)
        service._repo.create_plan.assert_called_once_with(data, previous_status="completed")
        assert result.cadence == "weekly"

    async def test_marks_previous_plan_completed_when_all_items_done(self, service):
        service._repo.get_active_plan.return_value = _make_plan_orm(items=[_make_item_orm(is_done=True)])
        service._repo.create_plan.return_value = _make_plan_orm()
        data = StudyPlanCreate(cadence="weekly", period_start=date(2026, 7, 31))
        await service.create_plan(data)
        service._repo.create_plan.assert_called_once_with(data, previous_status="completed")

    async def test_raises_when_active_plan_has_incomplete_items_and_not_forced(self, service):
        service._repo.get_active_plan.return_value = _make_plan_orm(items=[_make_item_orm(is_done=False)])
        data = StudyPlanCreate(cadence="weekly", period_start=date(2026, 7, 31))

        with pytest.raises(ActivePlanIncompleteError):
            await service.create_plan(data)

        service._repo.create_plan.assert_not_called()

    async def test_marks_previous_plan_abandoned_when_forced_with_incomplete_items(self, service):
        service._repo.get_active_plan.return_value = _make_plan_orm(items=[_make_item_orm(is_done=False)])
        service._repo.create_plan.return_value = _make_plan_orm()
        data = StudyPlanCreate(cadence="weekly", period_start=date(2026, 7, 31))
        await service.create_plan(data, force=True)
        service._repo.create_plan.assert_called_once_with(data, previous_status="abandoned")


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


class TestGetPlans:
    async def test_returns_plans_from_repo(self, service):
        service._repo.get_plans.return_value = [_make_plan_orm(id=1), _make_plan_orm(id=2, status="superseded")]
        filters = StudyPlanFilters(cadence="weekly", limit=20, offset=0)
        result = await service.get_plans(filters)
        service._repo.get_plans.assert_called_once_with(filters)
        assert [p.id for p in result] == [1, 2]
