from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from app.features.organizer.tasks.schemas import TaskCompletionRead, TaskRead, TaskCreate, TaskUpdate, TaskFilters
from app.api.auth import require_auth
from app.dependencies import TaskServiceDep

router = APIRouter(prefix="/organizer/tasks", tags=["organizer"], dependencies=[Depends(require_auth)])

@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def add_task(request: TaskCreate, service: TaskServiceDep):
    task_read = await service.create_task(request)
    return task_read

@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: int, request: TaskUpdate, service: TaskServiceDep):
    task_read = await service.update_task(task_id, request)
    return task_read


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, service: TaskServiceDep):
    await service.delete_task(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("", response_model=list[TaskRead])
async def get_tasks(service: TaskServiceDep, filters: TaskFilters = Depends()):
    return await service.get_tasks(filters)


@router.get("/history", response_model=list[TaskCompletionRead])
async def get_completions_history(
    service: TaskServiceDep,
    days: int = Query(90, ge=1, le=365),
):
    return await service.get_completions_history(days)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, service: TaskServiceDep):
    task_read = await service.get_task(task_id)
    if task_read is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task_read


@router.get("/{task_id}/completions", response_model=list[TaskCompletionRead])
async def get_task_completions(task_id: int, service: TaskServiceDep):
    result = await service.get_task_completions(task_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return result


@router.post("/{task_id}/complete", response_model=TaskRead)
async def complete_task(
    task_id: int,
    service: TaskServiceDep,
    occurrence_date: date | None = Query(None),
):
    result = await service.complete_task(task_id, occurrence_date)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if isinstance(result, TaskCompletionRead):
        task_read = await service.get_task(task_id)
        if task_read is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        task_read.is_done_today = True
        return task_read
    return result
