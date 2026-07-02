import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import require_auth
from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/integration/telegram",
    tags=["integrations"],
    dependencies=[Depends(require_auth)],
)

_TELEGRAM_API = "https://api.telegram.org"


class TelegramCommandEntry(BaseModel):
    command: str
    description: str


class TelegramSetCommandsResponse(BaseModel):
    ok: bool
    commands_registered: int
    commands: list[TelegramCommandEntry]


def _build_telegram_commands() -> list[TelegramCommandEntry]:
    entries = []
    for _cmd_type, actions in COMMAND_DEFINITIONS.items():
        for _action_name, config in actions.items():
            aliases = config.get("aliases", [])
            description = config.get("description", "")
            if not aliases or not description:
                continue
            command = aliases[0].lstrip("/").lower()
            entries.append(TelegramCommandEntry(command=command, description=description))
    return entries


@router.post("/set-commands", response_model=TelegramSetCommandsResponse)
async def set_telegram_commands() -> TelegramSetCommandsResponse:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TELEGRAM_BOT_TOKEN is not configured",
        )

    commands = _build_telegram_commands()
    payload = [c.model_dump() for c in commands]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_TELEGRAM_API}/bot{settings.telegram_bot_token}/setMyCommands",
            json={"commands": payload},
            timeout=10.0,
        )

    data = response.json()
    if not data.get("ok"):
        logger.error(
            "Telegram setMyCommands failed: status=%d body=%s",
            response.status_code,
            data,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Telegram API error: {data.get('description', 'unknown')}",
        )

    logger.info("Telegram setMyCommands: registered %d commands", len(commands))
    return TelegramSetCommandsResponse(
        ok=True,
        commands_registered=len(commands),
        commands=commands,
    )
