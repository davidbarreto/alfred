from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.study.plans.schemas import StudyPlanCreate, StudyPlanItemCreate
from app.features.study.plans.service import (
    ActivePlanCapReachedError,
    InvalidPlanTransitionError,
    StudyPlanService,
)

_NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _tag(name: str):
    tag = MagicMock()
    tag.name = name
    return tag


def _item_orm(**kwargs):
    item = MagicMock()
    item.id = kwargs.get("id", 1)
    item.plan_id = kwargs.get("plan_id", 1)
    item.description = kwargs.get("description", "Solve CF 1520E")
    item.url = kwargs.get("url")
    item.is_done = kwargs.get("is_done", False)
    item.position = kwargs.get("position", 0)
    item.source_type = kwargs.get("source_type", "manual")
    item.source_id = kwargs.get("source_id")
    item.reason = kwargs.get("reason")
    return item


def _plan_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.track_id = 1
    orm.title = kwargs.get("title", "Dynamic programming")
    orm.goal = "Solve medium DP problems without hints"
    orm.priority = kwargs.get("priority", "medium")
    orm.status = kwargs.get("status", "active")
    orm.activated_at = _NOW
    orm.completed_at = None
    orm.tags = kwargs.get("tags", [_tag("algorithms")])
    orm.items = kwargs.get("items", [])
    orm.created_at = _NOW
    orm.updated_at = _NOW
    return orm


def _create_data(**kwargs) -> StudyPlanCreate:
    return StudyPlanCreate(
        track_id=1,
        title=kwargs.get("title", "Dynamic programming"),
        goal="Solve medium DP problems without hints",
        tags=kwargs.get("tags", ["algorithms"]),
        items=kwargs.get("items", [StudyPlanItemCreate(description="Review DP basics")]),
    )


@pytest.fixture
def service():
    svc = StudyPlanService(session=AsyncMock())
    svc._repo = AsyncMock()
    svc._settings = AsyncMock()
    svc._settings.get_max_active_plans.return_value = 3
    return svc


class TestCreatePlan:
    async def test_goes_active_while_under_the_cap(self, service):
        service._repo.count_active_plans.return_value = 2
        service._repo.create_plan.return_value = _plan_orm()
        data = _create_data()

        result = await service.create_plan(data)

        service._repo.create_plan.assert_awaited_once_with(data, status="active")
        assert result.status == "active"

    async def test_goes_to_backlog_when_at_the_cap(self, service):
        service._repo.count_active_plans.return_value = 3
        service._repo.create_plan.return_value = _plan_orm(status="backlog")
        data = _create_data()

        result = await service.create_plan(data)

        service._repo.create_plan.assert_awaited_once_with(data, status="backlog")
        assert result.status == "backlog"

    async def test_respects_configured_cap(self, service):
        service._settings.get_max_active_plans.return_value = 1
        service._repo.count_active_plans.return_value = 1
        service._repo.create_plan.return_value = _plan_orm(status="backlog")

        await service.create_plan(_create_data())

        assert service._repo.create_plan.call_args.kwargs["status"] == "backlog"

    async def test_read_model_exposes_tag_names_and_item_sources(self, service):
        service._repo.count_active_plans.return_value = 0
        service._repo.create_plan.return_value = _plan_orm(
            tags=[_tag("algorithms"), _tag("dynamic-programming")],
            items=[_item_orm(source_type="cs_tag", reason="weakest tag")],
        )

        result = await service.create_plan(_create_data())

        assert result.tags == ["algorithms", "dynamic-programming"]
        assert result.items[0].source_type == "cs_tag"
        assert result.items[0].reason == "weakest tag"


class TestActivatePlan:
    async def test_activates_backlog_plan_under_the_cap(self, service):
        backlog = _plan_orm(status="backlog")
        service._repo.get_plan.return_value = backlog
        service._repo.count_active_plans.return_value = 2
        service._repo.set_status.return_value = _plan_orm(status="active")

        result = await service.activate_plan(1)

        service._repo.set_status.assert_awaited_once_with(backlog, "active")
        assert result.status == "active"

    async def test_raises_when_at_the_cap(self, service):
        service._repo.get_plan.return_value = _plan_orm(status="backlog")
        service._repo.count_active_plans.return_value = 3

        with pytest.raises(ActivePlanCapReachedError) as exc:
            await service.activate_plan(1)

        assert exc.value.max_active_plans == 3
        service._repo.set_status.assert_not_awaited()

    async def test_rejects_plan_that_is_not_in_backlog(self, service):
        service._repo.get_plan.return_value = _plan_orm(status="completed")

        with pytest.raises(InvalidPlanTransitionError):
            await service.activate_plan(1)

    async def test_returns_none_when_missing(self, service):
        service._repo.get_plan.return_value = None
        assert await service.activate_plan(99) is None


class TestCompleteAndAbandon:
    async def test_completes_active_plan(self, service):
        active = _plan_orm(status="active")
        service._repo.get_plan.return_value = active
        service._repo.set_status.return_value = _plan_orm(status="completed")

        result = await service.complete_plan(1)

        service._repo.set_status.assert_awaited_once_with(active, "completed")
        assert result.status == "completed"

    async def test_cannot_complete_backlog_plan(self, service):
        service._repo.get_plan.return_value = _plan_orm(status="backlog")

        with pytest.raises(InvalidPlanTransitionError):
            await service.complete_plan(1)

    @pytest.mark.parametrize("status", ["active", "backlog"])
    async def test_abandons_open_plan(self, service, status):
        plan = _plan_orm(status=status)
        service._repo.get_plan.return_value = plan
        service._repo.set_status.return_value = _plan_orm(status="abandoned")

        await service.abandon_plan(1)

        service._repo.set_status.assert_awaited_once_with(plan, "abandoned")

    async def test_cannot_abandon_closed_plan(self, service):
        service._repo.get_plan.return_value = _plan_orm(status="completed")

        with pytest.raises(InvalidPlanTransitionError):
            await service.abandon_plan(1)


class TestOverview:
    async def test_returns_active_backlog_and_cap(self, service):
        service._repo.get_active_plans.return_value = [_plan_orm(id=1)]
        service._repo.get_backlog_plans.return_value = [_plan_orm(id=2, status="backlog")]

        overview = await service.get_overview()

        assert [p.id for p in overview.active] == [1]
        assert [p.id for p in overview.backlog] == [2]
        assert overview.max_active_plans == 3


class TestDeleteAndItems:
    async def test_delete_returns_repo_result(self, service):
        service._repo.delete_plan.return_value = False
        assert await service.delete_plan(99) is False

    async def test_mark_item_done_true_when_found(self, service):
        service._repo.mark_item_done.return_value = _item_orm(is_done=True)
        assert await service.mark_item_done(1) is True

    async def test_mark_item_done_false_when_missing(self, service):
        service._repo.mark_item_done.return_value = None
        assert await service.mark_item_done(99) is False
