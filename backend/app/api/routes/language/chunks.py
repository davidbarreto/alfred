from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import ChunkServiceDep
from app.features.language.chunks.schemas import (
    ChunkCountRead,
    ChunkCreate,
    ChunkFilters,
    ChunkRead,
    ChunkUpdate,
    DailyBatchRead,
)

router = APIRouter(prefix="/language/chunks", tags=["language"], dependencies=[Depends(require_auth)])


@router.get("/daily-batch", response_model=list[DailyBatchRead])
async def get_daily_batch(
    service: ChunkServiceDep,
    track_id: int | None = None,
):
    return await service.get_daily_batch(track_id)


@router.post("", response_model=ChunkRead, status_code=status.HTTP_201_CREATED)
async def create_chunk(request: ChunkCreate, service: ChunkServiceDep):
    return await service.create_chunk(request)


@router.get("", response_model=list[ChunkRead])
async def get_chunks(service: ChunkServiceDep, filters: ChunkFilters = Depends()):
    return await service.get_chunks(filters)


@router.get("/count", response_model=ChunkCountRead)
async def count_chunks(service: ChunkServiceDep, filters: ChunkFilters = Depends()):
    count = await service.count_chunks(filters)
    return ChunkCountRead(count=count)


@router.get("/{chunk_id}", response_model=ChunkRead)
async def get_chunk(chunk_id: int, service: ChunkServiceDep):
    chunk = await service.get_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return chunk


@router.patch("/{chunk_id}", response_model=ChunkRead)
async def update_chunk(chunk_id: int, request: ChunkUpdate, service: ChunkServiceDep):
    chunk = await service.update_chunk(chunk_id, request)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return chunk


@router.post("/{chunk_id}/approve", response_model=ChunkRead)
async def approve_chunk(chunk_id: int, service: ChunkServiceDep):
    chunk = await service.approve_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return chunk


@router.delete("/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chunk(chunk_id: int, service: ChunkServiceDep):
    await service.delete_chunk(chunk_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
