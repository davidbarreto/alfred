from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.api.auth import require_auth
from app.dependencies import FileStorageDep, LanguageSessionServiceDep, ShadowingServiceDep
from app.features.language.sessions.schemas import (
    DailyProgressRead,
    SessionCreate,
    SessionFilters,
    SessionRead,
    ShadowingSessionCreate,
    SrsReviewCreate,
)

router = APIRouter(prefix="/language/sessions", tags=["language"], dependencies=[Depends(require_auth)])


@router.get("/daily-progress", response_model=list[DailyProgressRead])
async def get_daily_progress(
    service: LanguageSessionServiceDep,
    track_id: int | None = None,
):
    return await service.get_daily_progress(track_id)


@router.post("/srs-review", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def record_srs_review(request: SrsReviewCreate, service: LanguageSessionServiceDep):
    return await service.record_srs_review(request)


@router.post("/shadowing", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def record_shadowing(request: ShadowingSessionCreate, service: LanguageSessionServiceDep):
    return await service.record_shadowing(request)


@router.post("/shadowing/audio", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def record_shadowing_audio(
    service: ShadowingServiceDep,
    track_id: Annotated[int, Form()],
    chunk_id: Annotated[int | None, Form()] = None,
    audio: UploadFile = File(...),
):
    audio_bytes = await audio.read()
    return await service.record_shadowing_with_audio(track_id, chunk_id, audio_bytes)


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def record_session(request: SessionCreate, service: LanguageSessionServiceDep):
    return await service.record_session(request)


@router.get("", response_model=list[SessionRead])
async def get_sessions(service: LanguageSessionServiceDep, filters: SessionFilters = Depends()):
    return await service.get_sessions(filters)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: int, service: LanguageSessionServiceDep):
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.get("/{session_id}/audio")
async def get_session_audio(session_id: int, service: LanguageSessionServiceDep, storage: FileStorageDep):
    session = await service.get_session(session_id)
    if session is None or session.audio_ref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")
    audio = await storage.read(session.audio_ref)
    if audio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file missing")
    return Response(content=audio, media_type="audio/ogg")
