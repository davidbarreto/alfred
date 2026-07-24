from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.api.auth import require_auth
from app.dependencies import ConversationServiceDep, FileStorageDep
from app.features.language.conversation.schemas import (
    ConversationEndRead,
    ConversationStartCreate,
    ConversationStartRead,
    ConversationTurnResultRead,
)

router = APIRouter(prefix="/language/conversation", tags=["language"], dependencies=[Depends(require_auth)])


@router.post("/start", response_model=ConversationStartRead, status_code=status.HTTP_201_CREATED)
async def start_conversation(request: ConversationStartCreate, service: ConversationServiceDep):
    return await service.start(request.track_id, request.message_id, request.scenario, request.voice_reply)


@router.post("/turns/audio", response_model=ConversationTurnResultRead, status_code=status.HTTP_201_CREATED)
async def record_audio_turn(
    service: ConversationServiceDep,
    thread_id: Annotated[int, Form()],
    audio: UploadFile = File(...),
):
    audio_bytes = await audio.read()
    return await service.record_audio_turn(thread_id, audio_bytes)


@router.post("/{thread_id}/end", response_model=ConversationEndRead)
async def end_conversation(thread_id: int, service: ConversationServiceDep):
    return await service.end(thread_id)


@router.get("/turns/{turn_id}/audio")
async def get_turn_audio(turn_id: int, service: ConversationServiceDep, storage: FileStorageDep):
    audio_ref = await service.get_turn_audio_ref(turn_id)
    if audio_ref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")
    audio = await storage.read(audio_ref)
    if audio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file missing")
    return Response(content=audio, media_type="audio/ogg")
