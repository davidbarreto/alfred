from typing import Any, cast

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import parse_dt, parse_tags
from app.features.organizer.tasks.schemas import TaskCreate, TaskFilters, TaskPriorityFilter, TaskStatusFilter, TaskUpdate
from app.features.organizer.tasks.service import TaskService


async def handle_task(command: str, arguments: dict[str, Any], service: TaskService) -> Any:
    if command == "add":
        payload = TaskCreate(
            title=arguments.get("title", ""),
            priority=arguments.get("priority", "LOW"),
            deadline=parse_dt(arguments.get("deadline")),
            tags=parse_tags(arguments.get("tags")),
            recurrence_rule=arguments.get("recurrence"),
        )
        result = await service.create_task(payload)
        return result.model_dump()

    if command == "list":
        raw_status = arguments.get("status", "ALL")
        raw_priority = arguments.get("priority")
        filters = TaskFilters(
            status=cast(TaskStatusFilter, str(raw_status).upper()),
            priority=cast(TaskPriorityFilter, str(raw_priority).upper() if raw_priority else "ALL"),
            limit=int(arguments.get("limit", 100)),
        )
        results = await service.get_tasks(filters)
        return [r.model_dump() for r in results]

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
        if "tags" in arguments:
            update_fields["tags"] = parse_tags(arguments["tags"])
        if "recurrence" in arguments:
            update_fields["recurrence_rule"] = arguments["recurrence"]
        result = await service.update_task(task_id, TaskUpdate(**update_fields))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
        return result.model_dump()

    if command == "complete":
        task_id = int(arguments["id"])
        result = await service.update_task(task_id, TaskUpdate(status="DONE"))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
        return result.model_dump()

    if command == "delete":
        task_id = int(arguments["id"])
        await service.delete_task(task_id)
        return {"deleted": True, "id": task_id}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown task command: {command}")
