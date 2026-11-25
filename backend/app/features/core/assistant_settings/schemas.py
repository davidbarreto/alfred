from typing import Optional

from pydantic import BaseModel, field_validator

from app.features.core.settings.metadata import setting

USER_NAME_MAX_LENGTH = 50
PERSONA_ADDITIONS_MAX_LENGTH = 20000


class AssistantSettingsRead(BaseModel):
    """Who the user is, for the prompts. Both fields are personal, so they live in core.settings, never in git."""

    user_name: Optional[str] = None
    persona_additions: Optional[str] = None
    # The committed base persona (app/assistant/persona.md), shown read-only so the additions can build on it.
    base_persona: str


class AssistantSettingsUpdate(BaseModel):
    """Partial update: a field left out is untouched; null or blank clears it."""

    user_name: Optional[str] = setting(
        "Your name", "How the chat and the briefings call you. Empty = \"the user\".", max_length=USER_NAME_MAX_LENGTH,
    )
    persona_additions: Optional[str] = setting(
        "Persona additions", "Markdown added after the base persona.",
        widget="link", href="/persona", max_length=PERSONA_ADDITIONS_MAX_LENGTH,
    )

    @field_validator("user_name")
    @classmethod
    def _one_line_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return " ".join(value.split()) or None

    @field_validator("persona_additions")
    @classmethod
    def _trimmed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None
