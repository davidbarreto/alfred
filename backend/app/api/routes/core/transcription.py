from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.auth import require_auth
from app.dependencies import TranscriptionServiceDep
from app.features.core.transcription.schemas import TranscriptionRead

router = APIRouter(prefix="/core/transcription", tags=["core"], dependencies=[Depends(require_auth)])


@router.post("", response_model=TranscriptionRead, status_code=status.HTTP_201_CREATED)
async def create_transcription(service: TranscriptionServiceDep, audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/ogg"
    return await service.transcribe(audio_bytes, mime_type)
