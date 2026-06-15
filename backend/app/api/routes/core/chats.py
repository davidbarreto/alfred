from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import ChatServiceDep, SessionServiceDep
from app.features.core.chats.schemas import ChatRequest, ChatResponse

router = APIRouter(
    prefix="/core/chats",
    tags=["core", "chats"],
    dependencies=[Depends(require_auth)],
)


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatServiceDep,
    session_service: SessionServiceDep,
) -> ChatResponse:
    reply = await service.chat(request)
    session = await session_service.get(request.session_id)
    return ChatResponse(
        response=reply,
        source=session.source if session else None,
        external_id=session.external_id if session else None,
    )
