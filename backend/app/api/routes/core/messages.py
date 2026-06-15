from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import MessageServiceDep, SessionServiceDep
from app.features.core.messages.schemas import (
    MessageCreate,
    MessageFilters,
    MessageIngestRequest,
    MessageIngestResponse,
    MessageRead,
)

router = APIRouter(prefix="/core/messages", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/", response_model=list[MessageRead])
async def list_messages(service: MessageServiceDep, filters: MessageFilters = Depends()):
    return await service.list(filters)


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(message_id: int, service: MessageServiceDep):
    obj = await service.get(message_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return obj


@router.post("/", response_model=MessageIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_message(
    data: MessageIngestRequest,
    session_service: SessionServiceDep,
    message_service: MessageServiceDep,
) -> MessageIngestResponse:
    session = await session_service.get_or_create_active(data.source, data.external_id)
    message = await message_service.create(
        MessageCreate(session_id=session.id, role="user", content=data.text, meta=data.meta)
    )
    return MessageIngestResponse(message_id=message.id, session_id=session.id)
