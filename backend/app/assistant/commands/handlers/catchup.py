import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.core.catchup.schemas import CatchupApply, CatchupRead, CatchupTask
from app.features.core.catchup.service import CatchupService

logger = logging.getLogger(__name__)


async def handle_catchup(command: str, arguments: dict[str, Any], catchup_service: CatchupService) -> Any:
    logger.debug("handle_catchup: command=%s", command)

    if command == "show":
        result = await catchup_service.get_suggestions()
        return {**result.model_dump(mode="json"), "text": _format(result)}

    if command == "apply":
        kind = str(arguments.get("kind") or "").strip().lower()
        if kind not in ("spread", "drop"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usage: /catchupapply spread, or /catchupapply drop <id,id,...>",
            )
        task_ids = _parse_ids(arguments.get("ids"))
        if kind == "drop" and not task_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="List the task ids to drop, e.g. /catchupapply drop 12,15 (see /catchup)",
            )
        result = await catchup_service.apply(
            CatchupApply(kind=kind, task_ids=task_ids if kind == "drop" else None)
        )
        return result.model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown catchup command: {command}")


def _parse_ids(raw: Any) -> list[int] | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return [int(part) for part in str(raw).replace(" ", "").split(",") if part]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task ids must be numbers, e.g. 12,15")


def _task_line(task: CatchupTask) -> str:
    overdue = f", overdue {task.days_overdue}d" if task.days_overdue else ""
    return f"- #{task.id} {task.title} ({task.priority}{overdue})"


def _format(result: CatchupRead) -> str:
    if not result.today_top and not result.suggestions:
        return "Nothing to catch up on: no overdue or urgent tasks."
    lines: list[str] = []
    if result.today_top:
        lines.append("Focus today:")
        lines.extend(_task_line(t) for t in result.today_top)
    for number, suggestion in enumerate(result.suggestions, start=1):
        lines.append("")
        lines.append(f"{number}) {suggestion.title}")
        lines.append(suggestion.detail)
        if suggestion.kind == "spread":
            lines.extend(
                f"- #{m.task_id} {m.title} -> {m.new_deadline:%a %d %b}" for m in suggestion.moves[:8]
            )
            if len(suggestion.moves) > 8:
                lines.append(f"+{len(suggestion.moves) - 8} more")
        else:
            lines.extend(_task_line(t) for t in suggestion.tasks[:8])
            if len(suggestion.tasks) > 8:
                lines.append(f"+{len(suggestion.tasks) - 8} more")
        if suggestion.command:
            lines.append(f"Apply: {suggestion.command}")
    return "\n".join(lines)
