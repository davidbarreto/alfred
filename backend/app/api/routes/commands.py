from fastapi import APIRouter, Depends

from app.assistant.commands.schemas import CommandResolveRequest, CommandResolveResponse
from app.assistant.commands.resolver import resolve
from app.api.auth import require_auth

router = APIRouter(prefix="/commands", tags=["commands"], dependencies=[Depends(require_auth)])

@router.post("/resolve", response_model=CommandResolveResponse)
async def resolve_command(request: CommandResolveRequest):
    return resolve(request.text, command=request.command, args=request.args)