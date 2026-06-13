from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import WorkingMemoryServiceDep
from app.features.core.working_memory.schemas import (
    WorkingMemoryCreate,
    WorkingMemoryFilters,
    WorkingMemoryRead,
)

router = APIRouter(
    prefix="/core/working-memory", tags=["core"], dependencies=[Depends(require_auth)]
)


@router.get("/", response_model=list[WorkingMemoryRead])
async def list_working_memory(
    service: WorkingMemoryServiceDep, filters: WorkingMemoryFilters = Depends()
):
    return await service.list(filters)


@router.get("/{item_id}", response_model=WorkingMemoryRead)
async def get_working_memory_item(item_id: int, service: WorkingMemoryServiceDep):
    obj = await service.get(item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Working memory item not found")
    return obj


@router.post("/", response_model=WorkingMemoryRead, status_code=status.HTTP_201_CREATED)
async def create_working_memory_item(data: WorkingMemoryCreate, service: WorkingMemoryServiceDep):
    return await service.create(data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_working_memory_item(item_id: int, service: WorkingMemoryServiceDep):
    deleted = await service.delete(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Working memory item not found")
