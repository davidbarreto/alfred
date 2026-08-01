import pytest

from app.config import get_settings
from app.dependencies import (
    get_audio_analysis_provider,
    get_calendar_event_service,
    get_contact_service,
    get_contacts_crud_service,
    get_conversation_provider,
    get_conversation_tts_service,
    get_extraction_llm_provider,
    get_exchange_rate_provider,
    get_holiday_provider,
    get_llm_provider,
    get_note_provider,
    get_null_calendar_provider,
    get_null_contacts_provider,
    get_pronunciation_service,
    get_task_provider,
    get_transcription_provider,
    get_weather_provider,
)
from app.integrations.null.audio_analysis_provider import NullAudioAnalysisProvider
from app.integrations.null.conversation_provider import NullConversationProvider
from app.integrations.null.exchange_rate_provider import NullExchangeRateProvider
from app.integrations.null.holiday_provider import NullHolidayProvider
from app.integrations.null.llm_provider import NullLlmProvider
from app.integrations.null.pronunciation_provider import NullPronunciationProvider
from app.integrations.null.storage_provider import NullStorageProvider
from app.integrations.null.transcription_provider import NullTranscriptionProvider
from app.integrations.null.weather_provider import NullWeatherProvider
from unittest.mock import AsyncMock

_CACHED = [
    get_settings,
    get_llm_provider,
    get_extraction_llm_provider,
    get_task_provider,
    get_note_provider,
    get_exchange_rate_provider,
    get_null_calendar_provider,
    get_null_contacts_provider,
    get_weather_provider,
]


class TestDisableIntegrations:

    def setup_method(self):
        for fn in _CACHED:
            fn.cache_clear()

    def teardown_method(self):
        import os

        os.environ.pop("DISABLE_INTEGRATIONS", None)
        for fn in _CACHED:
            fn.cache_clear()

    def test_llm_provider_is_null_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")

        assert isinstance(get_llm_provider(), NullLlmProvider)
        assert isinstance(get_extraction_llm_provider(), NullLlmProvider)

    def test_storage_provider_is_null_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")

        assert isinstance(get_task_provider(), NullStorageProvider)
        assert isinstance(get_note_provider(), NullStorageProvider)

    def test_exchange_rate_provider_is_null_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")

        assert isinstance(get_exchange_rate_provider(), NullExchangeRateProvider)

    @pytest.mark.asyncio
    async def test_calendar_event_service_uses_null_provider_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")
        get_settings.cache_clear()

        service = await get_calendar_event_service(session=AsyncMock())

        assert service._provider is get_null_calendar_provider()

    @pytest.mark.asyncio
    async def test_contact_service_uses_null_provider_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")
        get_settings.cache_clear()

        service = await get_contact_service(session=AsyncMock())
        crud_service = await get_contacts_crud_service(session=AsyncMock())

        assert service is not None
        assert service._provider is get_null_contacts_provider()
        assert crud_service._provider is get_null_contacts_provider()

    def test_weather_and_holiday_providers_are_null_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")

        assert isinstance(get_weather_provider(), NullWeatherProvider)
        assert isinstance(get_holiday_provider(), NullHolidayProvider)

    def test_audio_providers_are_null_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")

        assert isinstance(get_audio_analysis_provider(), NullAudioAnalysisProvider)
        assert isinstance(get_conversation_provider(), NullConversationProvider)
        assert isinstance(get_transcription_provider(), NullTranscriptionProvider)

    def test_pronunciation_services_use_null_provider_when_integrations_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "true")

        assert isinstance(get_pronunciation_service()._client, NullPronunciationProvider)
        assert isinstance(get_conversation_tts_service()._client, NullPronunciationProvider)

    def test_llm_provider_raises_without_key_when_integrations_enabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_INTEGRATIONS", "false")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        get_settings.cache_clear()

        try:
            get_llm_provider()
        except RuntimeError as exc:
            assert "GEMINI_API_KEY" in str(exc)
        else:
            raise AssertionError("expected RuntimeError when GEMINI_API_KEY is unset")
