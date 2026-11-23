import logging
import pathlib
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.assistant_settings.schemas import AssistantSettingsRead, AssistantSettingsUpdate
from app.features.core.settings.service import SettingService

logger = logging.getLogger(__name__)

_KEY_PREFIX = "assistant."
_BASE_PERSONA_PATH = pathlib.Path(__file__).parents[3] / "assistant" / "persona.md"
_FALLBACK_PERSONA = "You are Alfred, a helpful personal AI assistant."
# How prompts refer to the user when no name is set.
DEFAULT_USER_LABEL = "the user"


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


@lru_cache(maxsize=1)
def base_persona() -> str:
    """The committed, generic persona every prompt starts from."""
    try:
        return _BASE_PERSONA_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Base persona missing at %s, using the one-line fallback", _BASE_PERSONA_PATH)
        return _FALLBACK_PERSONA


class AssistantSettingsService:
    """The user's name and persona additions; personal text that stays out of the repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> AssistantSettingsRead:
        return AssistantSettingsRead(
            user_name=await self._settings.get_value(_key("user_name")) or None,
            persona_additions=await self._settings.get_value(_key("persona_additions")) or None,
            base_persona=base_persona(),
        )

    async def update(self, data: AssistantSettingsUpdate) -> AssistantSettingsRead:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            await self._settings.set_value(_key(field), value or "")
        # Field names only: the values are personal.
        logger.info("Assistant settings updated: fields=%s", list(changes))
        return await self.get()

    async def user_label(self) -> str:
        """The user's name for prompts, or "the user" when none is set."""
        return await self._settings.get_value(_key("user_name")) or DEFAULT_USER_LABEL

    async def persona(self) -> str:
        """The chat persona: the base text, the user's name, then their additions."""
        settings = await self.get()
        parts = [settings.base_persona.rstrip()]
        if settings.user_name:
            parts.append(f"## The user\n\nThe user's name is {settings.user_name}.")
        if settings.persona_additions:
            parts.append(f"## Additions from the user\n\n{settings.persona_additions}")
        return "\n\n---\n\n".join(parts)
