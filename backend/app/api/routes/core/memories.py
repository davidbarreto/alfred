from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import MemoryServiceDep
from app.features.core.memories.schemas import (
    MemoryCreate,
    MemoryFilters,
    MemoryRead,
    MemoryUpdate,
)

router = APIRouter(prefix="/core/memories", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/", response_model=list[MemoryRead])
async def list_memories(service: MemoryServiceDep, filters: MemoryFilters = Depends()):
    return await service.list(filters)


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(memory_id: int, service: MemoryServiceDep):
    obj = await service.get(memory_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return obj


@router.post("/", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(data: MemoryCreate, service: MemoryServiceDep):
    return await service.create(data)


@router.patch("/{memory_id}", response_model=MemoryRead)
async def update_memory(memory_id: int, data: MemoryUpdate, service: MemoryServiceDep):
    obj = await service.update(memory_id, data)
    if obj is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return obj


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: int, service: MemoryServiceDep):
    deleted = await service.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
