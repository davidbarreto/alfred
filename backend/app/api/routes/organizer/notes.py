from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.features.organizer.notes.schemas import NoteRead, NoteCreate, NoteUpdate, NoteFilters
from app.api.auth import require_auth
from app.dependencies import NoteServiceDep

router = APIRouter(prefix="/organizer/notes", tags=["organizer"], dependencies=[Depends(require_auth)])


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def add_note(request: NoteCreate, service: NoteServiceDep):
    return await service.create_note(request)


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(note_id: int, request: NoteUpdate, service: NoteServiceDep):
    note_read = await service.update_note(note_id, request)
    if note_read is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note_read


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, service: NoteServiceDep):
    await service.delete_note(note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{note_id}/archive", response_model=NoteRead)
async def archive_note(note_id: int, service: NoteServiceDep):
    note_read = await service.archive_note(note_id)
    if note_read is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note_read


@router.post("/{note_id}/unarchive", response_model=NoteRead)
async def unarchive_note(note_id: int, service: NoteServiceDep):
    note_read = await service.unarchive_note(note_id)
    if note_read is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note_read


@router.get("", response_model=list[NoteRead])
async def get_notes(service: NoteServiceDep, filters: NoteFilters = Depends()):
    return await service.get_notes(filters)


@router.get("/{note_id}", response_model=NoteRead)
async def get_note(note_id: int, service: NoteServiceDep):
    note_read = await service.get_note(note_id)
    if note_read is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note_read
