from fastapi import APIRouter

from app.schemas.command import CommandResolveRequest, CommandResolveResponse
from app.services.command import CommandService

router = APIRouter(prefix="/commands", tags=["commands"])

@router.post("/resolve", response_model=CommandResolveResponse)
async def resolve_command(request: CommandResolveRequest):
    return CommandService.resolve(request.text)