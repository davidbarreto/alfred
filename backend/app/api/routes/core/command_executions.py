from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CommandExecutionServiceDep
from app.features.core.command_executions.schemas import (
    CommandExecutionCreate,
    CommandExecutionFilters,
    CommandExecutionRead,
    CommandExecutionUpdate,
)

router = APIRouter(
    prefix="/core/command-executions", tags=["core"], dependencies=[Depends(require_auth)]
)


@router.get("/", response_model=list[CommandExecutionRead])
async def list_command_executions(
    service: CommandExecutionServiceDep, filters: CommandExecutionFilters = Depends()
):
    return await service.list(filters)


@router.get("/{execution_id}", response_model=CommandExecutionRead)
async def get_command_execution(execution_id: int, service: CommandExecutionServiceDep):
    obj = await service.get(execution_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Command execution not found")
    return obj


@router.post("/", response_model=CommandExecutionRead, status_code=status.HTTP_201_CREATED)
async def create_command_execution(data: CommandExecutionCreate, service: CommandExecutionServiceDep):
    return await service.create(data)


@router.patch("/{execution_id}", response_model=CommandExecutionRead)
async def update_command_execution(
    execution_id: int, data: CommandExecutionUpdate, service: CommandExecutionServiceDep
):
    obj = await service.update(execution_id, data)
    if obj is None:
        raise HTTPException(status_code=404, detail="Command execution not found")
    return obj
