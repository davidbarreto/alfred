import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.study.plans.schemas import StudyPlanRead
from app.features.study.plans.service import StudyPlanService

logger = logging.getLogger(__name__)

_PENDING_ITEMS_SHOWN = 5


def _plan_summary(plan: StudyPlanRead) -> dict[str, Any]:
    pending = [item.description for item in plan.items if not item.is_done]
    return {
        "id": plan.id,
        "title": plan.title,
        "goal": plan.goal,
        "priority": plan.priority,
        "done": len(plan.items) - len(pending),
        "total": len(plan.items),
        "pending_items": pending[:_PENDING_ITEMS_SHOWN],
    }


def _format_overview(active: list[StudyPlanRead], backlog: list[StudyPlanRead], max_active_plans: int) -> str:
    if not active and not backlog:
        return "No study plans yet."
    lines = [f"Active study plans ({len(active)}/{max_active_plans}):"]
    for plan in active:
        done = sum(1 for item in plan.items if item.is_done)
        lines.append(f"- #{plan.id} {plan.title} ({done}/{len(plan.items)} done)")
    if backlog:
        lines.append(f"Backlog ({len(backlog)}):")
        lines.extend(f"- #{plan.id} {plan.title} [{plan.priority}]" for plan in backlog)
    return "\n".join(lines)


async def handle_study(command: str, arguments: dict[str, Any], plan_service: StudyPlanService) -> Any:
    logger.debug("handle_study: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "plans":
        overview = await plan_service.get_overview()
        return {
            "active": [_plan_summary(plan) for plan in overview.active],
            "backlog": [_plan_summary(plan) for plan in overview.backlog],
            "max_active_plans": overview.max_active_plans,
            "message": _format_overview(overview.active, overview.backlog, overview.max_active_plans),
        }

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown study command: {command}")
