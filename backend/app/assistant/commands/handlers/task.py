import logging
from datetime import date, datetime, timezone
from typing import Any, cast

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import parse_dt, parse_tags
from app.features.core.embeddings.schemas import EmbeddingSearchRequest
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.reminders.service import snooze_undated_escalation
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.organizer.tasks.schemas import (
    TaskCompletionRead,
    TaskCreate,
    TaskFilters,
    TaskPriorityFilter,
    TaskRead,
    TaskStatusFilter,
    TaskUpdate,
)
from app.features.organizer.tasks.service import TaskService

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _parse_occurrence_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    dt = parse_dt(str(raw))
    return dt.date() if dt is not None else None


async def handle_task(
    command: str,
    arguments: dict[str, Any],
    service: TaskService,
    embedding_service: EmbeddingService | None = None,
    working_memory_service: WorkingMemoryService | None = None,
) -> Any:
    logger.debug("handle_task: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "add":
        payload = TaskCreate(
            title=arguments.get("title", ""),
            priority=arguments.get("priority", "LOW"),
            deadline=parse_dt(arguments.get("deadline")),
            tags=parse_tags(arguments.get("tags")),
            recurrence_rule=arguments.get("recurrence"),
        )
        result = await service.create_task(payload)
        return result.model_dump(mode='json')

    if command == "search":
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task search requires a query")
        if embedding_service is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Embedding service not available")
        results = await embedding_service.search(
            EmbeddingSearchRequest(query=query, source_types=["task"], limit=10, threshold=0.4)
        )
        logger.debug("handle_task search: query=%r results=%d", query, len(results))
        return [{"source_id": r.source_id, "content": r.content, "similarity": r.similarity} for r in results]

    if command == "pending":
        now = datetime.now(timezone.utc)
        today = now.date()
        filters = TaskFilters(status="ALL", limit=200)
        all_tasks = await service.get_tasks(filters)
        active = [t for t in all_tasks if t.status in ("TODO", "DOING")]
        overdue = sorted(
            [t for t in active if t.deadline and t.deadline.date() < today],
            key=lambda t: (t.deadline, _PRIORITY_ORDER.get(t.priority, 99)),
        )
        due_today = sorted(
            [t for t in active if t.deadline and t.deadline.date() == today],
            key=lambda t: (_PRIORITY_ORDER.get(t.priority, 99), t.deadline),
        )
        logger.debug("handle_task pending: overdue=%d due_today=%d", len(overdue), len(due_today))
        return {
            "overdue": [t.model_dump(mode='json') for t in overdue],
            "due_today": [t.model_dump(mode='json') for t in due_today],
            "overdue_count": len(overdue),
            "due_today_count": len(due_today),
            "total": len(overdue) + len(due_today),
        }

    if command == "list":
        raw_status = arguments.get("status", "ACTIVE")
        raw_priority = arguments.get("priority")
        filters = TaskFilters(
            status=cast(TaskStatusFilter, str(raw_status).upper()),
            priority=cast(TaskPriorityFilter, str(raw_priority).upper() if raw_priority else "ALL"),
            limit=int(arguments.get("limit", 100)),
        )
        results = await service.get_tasks(filters)
        return [r.model_dump(mode='json') for r in results]

    if command == "update":
        task_id = int(arguments["id"])
        update_fields: dict[str, Any] = {}
        if "title" in arguments:
            update_fields["title"] = arguments["title"]
        if "priority" in arguments:
            update_fields["priority"] = arguments["priority"]
        if "deadline" in arguments:
            update_fields["deadline"] = parse_dt(arguments["deadline"])
        if "status" in arguments:
            update_fields["status"] = str(arguments["status"]).upper()
        if "urgency" in arguments:
            update_fields["urgency"] = str(arguments["urgency"]).upper()
        if "tags" in arguments:
            update_fields["tags"] = parse_tags(arguments["tags"])
        if "recurrence" in arguments:
            update_fields["recurrence_rule"] = arguments["recurrence"]
        result = await service.update_task(task_id, TaskUpdate(**update_fields))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
        return result.model_dump(mode='json')

    if command == "complete":
        task_id = int(arguments["id"])
        occurrence_date = _parse_occurrence_date(arguments.get("occurrence_date"))
        result = await service.complete_task(task_id, occurrence_date)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
        if isinstance(result, TaskCompletionRead):
            return {"success": True, "occurrence_date": str(result.occurrence_date), "task_id": task_id}
        return result.model_dump(mode='json')

    if command == "cancel":
        task_id = int(arguments["id"])
        try:
            result = await service.cancel_task(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
        return result.model_dump(mode='json')

    if command == "delete":
        task_id = int(arguments["id"])
        await service.delete_task(task_id)
        return {"deleted": True, "id": task_id}

    if command == "snooze":
        task_id = int(arguments["id"])
        existing = await service.get_task(task_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
        if working_memory_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Working memory service not available"
            )

        days = int(arguments["days"]) if arguments.get("days") else None
        expires_at = await snooze_undated_escalation(working_memory_service, task_id, days)
        return {"id": task_id, "snoozed_until": expires_at.isoformat()}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown task command: {command}")
