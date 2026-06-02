from fastapi import APIRouter, Depends

from app.schemas.command import CommandResolveRequest, CommandResolveResponse
from app.services.command import CommandService
from app.api.auth import require_auth

router = APIRouter(prefix="/commands", tags=["commands"], dependencies=[Depends(require_auth)])

@router.post("/resolve", response_model=CommandResolveResponse)
async def resolve_command(request: CommandResolveRequest):
    return CommandService.resolve(request.text)