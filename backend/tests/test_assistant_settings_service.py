from unittest.mock import AsyncMock

import pytest

from app.features.core.assistant_settings.schemas import AssistantSettingsUpdate
from app.features.core.assistant_settings.service import AssistantSettingsService, base_persona


@pytest.fixture
def stored():
    return {}


@pytest.fixture
def service(stored):
    svc = AssistantSettingsService(session=AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.side_effect = lambda key, default=None: stored.get(key, default)

    async def set_value(key, value):
        stored[key] = value

    svc._settings.set_value.side_effect = set_value
    return svc


class TestBasePersona:
    def test_is_the_committed_generic_file(self):
        persona = base_persona()

        assert persona.startswith("# Alfred")
        assert "## Core Philosophy" in persona


class TestGetAndUpdate:
    async def test_unset_values_are_none(self, service):
        settings = await service.get()

        assert settings.user_name is None and settings.persona_additions is None
        assert settings.base_persona == base_persona()

    async def test_update_stores_trimmed_values_under_the_assistant_prefix(self, service, stored):
        await service.update(AssistantSettingsUpdate(user_name="  Sam   Doe ", persona_additions="\n Likes jazz. \n"))

        assert stored == {"assistant.user_name": "Sam Doe", "assistant.persona_additions": "Likes jazz."}

    async def test_null_or_blank_clears_and_unset_fields_are_untouched(self, service, stored):
        stored.update({"assistant.user_name": "Sam", "assistant.persona_additions": "Likes jazz."})

        result = await service.update(AssistantSettingsUpdate(persona_additions="   "))

        assert stored["assistant.persona_additions"] == ""
        assert result.persona_additions is None
        assert result.user_name == "Sam"

    def test_name_length_is_capped(self):
        with pytest.raises(ValueError):
            AssistantSettingsUpdate(user_name="x" * 51)


class TestPromptHelpers:
    async def test_user_label_defaults_to_the_user(self, service, stored):
        assert await service.user_label() == "the user"
        stored["assistant.user_name"] = "Sam"
        assert await service.user_label() == "Sam"

    async def test_persona_is_the_base_alone_when_nothing_is_set(self, service):
        assert await service.persona() == base_persona().rstrip()

    async def test_persona_adds_name_then_additions_after_the_base(self, service, stored):
        stored.update({"assistant.user_name": "Sam", "assistant.persona_additions": "Sam plays the cello."})

        persona = await service.persona()

        assert persona.startswith(base_persona().rstrip())
        name_at = persona.index("The user's name is Sam.")
        additions_at = persona.index("## Additions from the user\n\nSam plays the cello.")
        assert name_at < additions_at
