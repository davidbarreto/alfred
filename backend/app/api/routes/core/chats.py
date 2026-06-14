from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import ChatServiceDep
from app.features.core.chats.schemas import ChatRequest, ChatResponse

router = APIRouter(
    prefix="/core/chats",
    tags=["core", "chats"],
    dependencies=[Depends(require_auth)],
)


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, service: ChatServiceDep) -> ChatResponse:
    response = await service.chat(request)
    return ChatResponse(response=response)
