from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.study import handle_study
from app.features.study.plans.schemas import StudyPlanItemRead, StudyPlanRead, StudyPlansOverview

_NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _item(id: int, description: str, is_done: bool = False) -> StudyPlanItemRead:
    return StudyPlanItemRead(
        id=id, description=description, url=None, is_done=is_done, position=id,
        source_type="manual", source_id=None, reason=None,
    )


def _plan(id: int, title: str, status: str = "active", priority: str = "medium", items=None) -> StudyPlanRead:
    return StudyPlanRead(
        id=id, track_id=1, title=title, goal="goal", priority=priority, status=status,
        activated_at=_NOW, completed_at=None, tags=[], items=items or [],
        created_at=_NOW, updated_at=_NOW,
    )


@pytest.fixture
def plan_service():
    return AsyncMock()


class TestHandleStudyPlans:
    async def test_lists_active_and_backlog(self, plan_service):
        plan_service.get_overview.return_value = StudyPlansOverview(
            active=[_plan(1, "Dynamic programming", items=[_item(1, "Review DP", is_done=True), _item(2, "Solve 1520E")])],
            backlog=[_plan(2, "CAP theorem", status="backlog", priority="high")],
            max_active_plans=3,
        )

        result = await handle_study("plans", {}, plan_service)

        assert result["active"][0]["pending_items"] == ["Solve 1520E"]
        assert result["active"][0]["done"] == 1
        assert result["backlog"][0]["title"] == "CAP theorem"
        assert "Active study plans (1/3):" in result["message"]
        assert "#1 Dynamic programming (1/2 done)" in result["message"]
        assert "#2 CAP theorem [high]" in result["message"]

    async def test_empty_message_when_no_plans(self, plan_service):
        plan_service.get_overview.return_value = StudyPlansOverview(active=[], backlog=[], max_active_plans=3)

        result = await handle_study("plans", {}, plan_service)

        assert result["message"] == "No study plans yet."

    async def test_unknown_command_is_400(self, plan_service):
        with pytest.raises(HTTPException) as exc:
            await handle_study("gaps", {}, plan_service)
        assert exc.value.status_code == 400
