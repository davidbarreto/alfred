import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import require_auth
from app.dependencies import DbSessionDep, EmbeddingServiceDep
from app.features.core.embeddings.schemas import (
    EmbeddingCreate,
    EmbeddingRead,
    EmbeddingSearchRequest,
    EmbeddingSearchResult,
)
from app.features.organizer.notes.repository import NoteRepository
from app.features.organizer.notes.schemas import NoteFilters
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TaskFilters

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/core/embeddings", tags=["core"], dependencies=[Depends(require_auth)])


class BackfillResponse(BaseModel):
    notes_embedded: int
    tasks_embedded: int
    errors: int


@router.post("/", response_model=EmbeddingRead, status_code=status.HTTP_201_CREATED)
async def create_embedding(data: EmbeddingCreate, service: EmbeddingServiceDep):
    return await service.embed(data)


@router.post("/search", response_model=list[EmbeddingSearchResult])
async def search_embeddings(request: EmbeddingSearchRequest, service: EmbeddingServiceDep):
    return await service.search(request)


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_embeddings(service: EmbeddingServiceDep, session: DbSessionDep):
    """Embed all existing notes and tasks that are missing embeddings. Safe to re-run (upserts)."""
    notes_embedded = 0
    tasks_embedded = 0
    errors = 0

    notes = await NoteRepository(session).get_notes(NoteFilters(limit=10_000))
    for note in notes:
        try:
            content = f"{note.title}: {note.content}" if note.content and note.content != note.title else note.title
            await service.embed(EmbeddingCreate(source_type="note", source_id=note.id, content=content))
            notes_embedded += 1
        except Exception as exc:
            logger.warning("Backfill note embed failed: id=%d error=%s", note.id, exc)
            errors += 1

    tasks = await TaskRepository(session).get_tasks(TaskFilters(status="ALL", limit=10_000))
    for task in tasks:
        try:
            await service.embed(EmbeddingCreate(source_type="task", source_id=task.id, content=task.title))
            tasks_embedded += 1
        except Exception as exc:
            logger.warning("Backfill task embed failed: id=%d error=%s", task.id, exc)
            errors += 1

    logger.info("Backfill complete: notes=%d tasks=%d errors=%d", notes_embedded, tasks_embedded, errors)
    return BackfillResponse(notes_embedded=notes_embedded, tasks_embedded=tasks_embedded, errors=errors)


@router.delete("/{embedding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_embedding(embedding_id: int, service: EmbeddingServiceDep):
    deleted = await service.delete(embedding_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Embedding not found")
