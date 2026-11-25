import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.features.core.chat_settings.schemas import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_MEMORY_DEDUP_THRESHOLD,
    DEFAULT_MEMORY_IMPORTANCE_BUMP,
    DEFAULT_MEMORY_LIMIT,
    DEFAULT_MEMORY_THRESHOLD,
    DEFAULT_RECALL_LIMIT,
    DEFAULT_RECALL_THRESHOLD,
    ChatSettingsRead,
    ChatSettingsUpdate,
)
from app.features.core.settings.service import SettingService

logger = logging.getLogger(__name__)

_KEY_PREFIX = "chat."

DEFAULTS: dict[str, int | float] = {
    "history_limit": DEFAULT_HISTORY_LIMIT,
    "memory_limit": DEFAULT_MEMORY_LIMIT,
    "memory_threshold": DEFAULT_MEMORY_THRESHOLD,
    "recall_threshold": DEFAULT_RECALL_THRESHOLD,
    "recall_limit": DEFAULT_RECALL_LIMIT,
    "memory_dedup_threshold": DEFAULT_MEMORY_DEDUP_THRESHOLD,
    "memory_importance_bump": DEFAULT_MEMORY_IMPORTANCE_BUMP,
}


def defaults() -> dict[str, int | float]:
    """Every field's default: `DEFAULTS` plus the four that come from env (the portal value wins over them)."""
    env = get_settings()
    return {
        **DEFAULTS,
        "temperature": env.llm_chat_temperature,
        "intent_threshold": env.intent_threshold,
        "intent_shortlist_floor": env.intent_shortlist_floor,
        "intent_shortlist_k": env.intent_shortlist_k,
    }


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class ChatSettingsService:
    """Chat, recall, memory and intent-detection tuning, read when used so a change applies on the next message."""

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> ChatSettingsRead:
        values: dict[str, int | float] = {}
        for field, default in defaults().items():
            raw = await self._settings.get_value(_key(field))
            values[field] = type(default)(raw) if raw else default
        return ChatSettingsRead(**values)

    async def update(self, data: ChatSettingsUpdate) -> ChatSettingsRead:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in changes.items():
            await self._settings.set_value(_key(field), str(value))
        logger.info("Chat settings updated: fields=%s", list(changes))
        return await self.get()
