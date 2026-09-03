from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewStageServiceDep
from app.features.organizer.contacts.schemas import ContactRead
from app.features.organizer.interviews.stages.schemas import (
    InterviewStageCreate,
    InterviewStageFilters,
    InterviewStageRead,
    InterviewStageUpdate,
    StageContactLink,
)
from app.features.organizer.notes.schemas import NoteRead
from app.features.organizer.tasks.schemas import TaskRead

router = APIRouter(
    prefix="/organizer/interview-stages",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[InterviewStageRead])
async def get_stages(
    service: InterviewStageServiceDep,
    filters: InterviewStageFilters = Depends(),
) -> list[InterviewStageRead]:
    return await service.get_stages(filters)


@router.get("/{stage_id}", response_model=InterviewStageRead)
async def get_stage(stage_id: int, service: InterviewStageServiceDep) -> InterviewStageRead:
    stage = await service.get_stage(stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview stage not found")
    return stage


@router.post("", response_model=InterviewStageRead, status_code=status.HTTP_201_CREATED)
async def create_stage(request: InterviewStageCreate, service: InterviewStageServiceDep) -> InterviewStageRead:
    return await service.create_stage(request)


@router.patch("/{stage_id}", response_model=InterviewStageRead)
async def update_stage(
    stage_id: int, request: InterviewStageUpdate, service: InterviewStageServiceDep
) -> InterviewStageRead:
    stage = await service.update_stage(stage_id, request)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview stage not found")
    return stage


@router.delete("/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(stage_id: int, service: InterviewStageServiceDep) -> Response:
    await service.delete_stage(stage_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{stage_id}/contacts/{contact_id}", status_code=status.HTTP_201_CREATED)
async def add_stage_contact(
    stage_id: int, contact_id: int, request: StageContactLink, service: InterviewStageServiceDep
) -> Response:
    await service.add_stage_contact(stage_id, contact_id, request.role)
    return Response(status_code=status.HTTP_201_CREATED)


@router.delete("/{stage_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_stage_contact(stage_id: int, contact_id: int, service: InterviewStageServiceDep) -> Response:
    await service.remove_stage_contact(stage_id, contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{stage_id}/contacts", response_model=list[ContactRead])
async def list_stage_contacts(stage_id: int, service: InterviewStageServiceDep) -> list[ContactRead]:
    return await service.list_stage_contacts(stage_id)


@router.post("/{stage_id}/tasks/{task_id}", status_code=status.HTTP_201_CREATED)
async def link_stage_task(stage_id: int, task_id: int, service: InterviewStageServiceDep) -> Response:
    await service.link_task(stage_id, task_id)
    return Response(status_code=status.HTTP_201_CREATED)


@router.delete("/{stage_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_stage_task(stage_id: int, task_id: int, service: InterviewStageServiceDep) -> Response:
    await service.unlink_task(stage_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{stage_id}/tasks", response_model=list[TaskRead])
async def list_stage_tasks(stage_id: int, service: InterviewStageServiceDep) -> list[TaskRead]:
    return await service.list_tasks(stage_id)


@router.post("/{stage_id}/notes/{note_id}", status_code=status.HTTP_201_CREATED)
async def link_stage_note(stage_id: int, note_id: int, service: InterviewStageServiceDep) -> Response:
    await service.link_note(stage_id, note_id)
    return Response(status_code=status.HTTP_201_CREATED)


@router.delete("/{stage_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_stage_note(stage_id: int, note_id: int, service: InterviewStageServiceDep) -> Response:
    await service.unlink_note(stage_id, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{stage_id}/notes", response_model=list[NoteRead])
async def list_stage_notes(stage_id: int, service: InterviewStageServiceDep) -> list[NoteRead]:
    return await service.list_notes(stage_id)
