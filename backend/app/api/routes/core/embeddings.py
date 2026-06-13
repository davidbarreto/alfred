from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import EmbeddingServiceDep
from app.features.core.embeddings.schemas import (
    EmbeddingCreate,
    EmbeddingRead,
    EmbeddingSearchRequest,
    EmbeddingSearchResult,
)

router = APIRouter(prefix="/core/embeddings", tags=["core"], dependencies=[Depends(require_auth)])


@router.post("/", response_model=EmbeddingRead, status_code=status.HTTP_201_CREATED)
async def create_embedding(data: EmbeddingCreate, service: EmbeddingServiceDep):
    return await service.embed(data)


@router.post("/search", response_model=list[EmbeddingSearchResult])
async def search_embeddings(request: EmbeddingSearchRequest, service: EmbeddingServiceDep):
    return await service.search(request)


@router.delete("/{embedding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_embedding(embedding_id: int, service: EmbeddingServiceDep):
    deleted = await service.delete(embedding_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Embedding not found")
