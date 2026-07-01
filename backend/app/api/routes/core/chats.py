import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.auth import require_auth
from app.config import get_settings
from app.dependencies import ChatServiceDep, SessionServiceDep
from app.features.core.chats.schemas import ChatRequest, ChatResponse

router = APIRouter(
    prefix="/core/chats",
    tags=["core", "chats"],
    dependencies=[Depends(require_auth)],
)

# Separate router for SSE stream — auth handled via query param inside the
# handler so browser fetch/EventSource can include it without custom headers.
stream_router = APIRouter(prefix="/core/chats", tags=["core", "chats"])


@router.post("", response_model=ChatResponse)
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


@stream_router.get("/stream")
async def chat_stream(
    session_id: int,
    service: ChatServiceDep,
    token: str = Query(default=""),
) -> StreamingResponse:
    if token != get_settings().alfred_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    async def _generate():
        try:
            async for chunk in service.stream_chat(ChatRequest(session_id=session_id)):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception:
            yield f"data: {json.dumps({'error': 'Stream failed'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
