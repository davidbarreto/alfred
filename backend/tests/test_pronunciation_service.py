import pytest
from unittest.mock import AsyncMock, MagicMock

from app.features.language.chunks.pronunciation_service import PronunciationService
from app.shared.pronunciation import TtsAudioResult


def _make_service(**kwargs):
    client = kwargs.get("client") or AsyncMock()
    converter = kwargs.get("converter") or AsyncMock()
    storage = kwargs.get("storage") or AsyncMock()
    fetched = kwargs.get("fetched_result") or TtsAudioResult(
        audio=kwargs.get("fetched_audio", b"fake-mp3-bytes"),
        tokens_input=kwargs.get("tokens_input"),
        tokens_output=kwargs.get("tokens_output"),
        finish_reason=kwargs.get("finish_reason"),
    )
    client.get_audio.return_value = fetched
    converter.to_ogg_opus.return_value = kwargs.get("converted_audio", b"fake-ogg-bytes")
    storage.read.return_value = kwargs.get("cached_audio", None)
    service = PronunciationService(client, converter, storage, cache_namespace=kwargs.get("cache_namespace", "pronunciation_cache"))
    return service, client, converter, storage


class TestProviderIdentity:

    def test_proxies_provider_and_model_from_client(self):
        client = MagicMock()
        client.provider = "google"
        client.model = "gemini-2.5-flash-tts"
        service, _, _, _ = _make_service(client=client)

        assert service.provider == "google"
        assert service.model == "gemini-2.5-flash-tts"

    def test_falls_back_to_unknown_when_client_lacks_identity(self):
        client = AsyncMock(spec=["get_audio"])
        service, _, _, _ = _make_service(client=client)

        assert service.provider == "unknown"
        assert service.model == "unknown"


class TestGetAudio:

    @pytest.mark.asyncio
    async def test_defaults_to_mp3_without_conversion(self):
        service, client, converter, storage = _make_service()

        result, content_type = await service.get_audio("bonjour", "fr")

        assert result.audio == b"fake-mp3-bytes"
        assert content_type == "audio/mpeg"
        client.get_audio.assert_awaited_once_with("bonjour", "fr")
        converter.to_ogg_opus.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_requesting_ogg_converts_the_fetched_audio(self):
        service, client, converter, storage = _make_service()

        result, content_type = await service.get_audio("bonjour", "fr", audio_format="ogg")

        assert result.audio == b"fake-ogg-bytes"
        assert content_type == "audio/ogg"
        converter.to_ogg_opus.assert_awaited_once_with(b"fake-mp3-bytes")

    @pytest.mark.asyncio
    async def test_requesting_mp3_explicitly_skips_conversion(self):
        service, client, converter, storage = _make_service()

        result, content_type = await service.get_audio("bonjour", "fr", audio_format="mp3")

        assert result.audio == b"fake-mp3-bytes"
        assert content_type == "audio/mpeg"
        converter.to_ogg_opus.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_client_and_converter(self):
        service, client, converter, storage = _make_service(cached_audio=b"cached-bytes")

        result, content_type = await service.get_audio("bonjour", "fr", audio_format="ogg")

        assert result.audio == b"cached-bytes"
        assert content_type == "audio/ogg"
        client.get_audio.assert_not_awaited()
        converter.to_ogg_opus.assert_not_awaited()
        storage.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_hit_reports_no_call_metadata(self):
        service, client, converter, storage = _make_service(
            cached_audio=b"cached-bytes", tokens_input=99, finish_reason="STOP"
        )

        result, _ = await service.get_audio("bonjour", "fr", audio_format="ogg")

        assert result.tokens_input is None
        assert result.finish_reason is None

    @pytest.mark.asyncio
    async def test_cache_miss_passes_through_call_metadata(self):
        service, client, converter, storage = _make_service(tokens_input=12, tokens_output=7, finish_reason="STOP")

        result, _ = await service.get_audio("bonjour", "fr", audio_format="ogg")

        assert result.tokens_input == 12
        assert result.tokens_output == 7
        assert result.finish_reason == "STOP"

    @pytest.mark.asyncio
    async def test_cache_miss_saves_result_for_next_time(self):
        service, client, converter, storage = _make_service()

        await service.get_audio("bonjour", "fr", audio_format="ogg")

        storage.save.assert_awaited_once()
        args = storage.save.call_args.args
        assert args[0] == b"fake-ogg-bytes"
        assert args[1].startswith("pronunciation_cache/fr/")
        assert args[1].endswith(".ogg")

    @pytest.mark.asyncio
    async def test_cache_key_is_stable_for_same_text_lang_format(self):
        service, client, converter, storage = _make_service()

        await service.get_audio("bonjour", "fr", audio_format="mp3")
        first_key = storage.read.call_args.args[0]
        await service.get_audio("bonjour", "fr", audio_format="mp3")
        second_key = storage.read.call_args.args[0]

        assert first_key == second_key

    @pytest.mark.asyncio
    async def test_custom_cache_namespace_keeps_providers_from_colliding(self):
        service, client, converter, storage = _make_service(cache_namespace="conversation_tts_cache")

        await service.get_audio("bonjour", "fr", audio_format="ogg")

        cache_key = storage.read.call_args.args[0]
        assert cache_key.startswith("conversation_tts_cache/fr/")
