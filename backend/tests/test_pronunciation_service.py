import pytest
from unittest.mock import AsyncMock

from app.features.language.chunks.pronunciation_service import PronunciationService


def _make_service(**kwargs):
    client = kwargs.get("client") or AsyncMock()
    converter = kwargs.get("converter") or AsyncMock()
    storage = kwargs.get("storage") or AsyncMock()
    client.get_audio.return_value = kwargs.get("fetched_audio", b"fake-mp3-bytes")
    converter.to_ogg_opus.return_value = kwargs.get("converted_audio", b"fake-ogg-bytes")
    storage.read.return_value = kwargs.get("cached_audio", None)
    return PronunciationService(client, converter, storage), client, converter, storage


class TestGetAudio:

    @pytest.mark.asyncio
    async def test_defaults_to_mp3_without_conversion(self):
        service, client, converter, storage = _make_service()

        audio, content_type = await service.get_audio("bonjour", "fr")

        assert audio == b"fake-mp3-bytes"
        assert content_type == "audio/mpeg"
        client.get_audio.assert_awaited_once_with("bonjour", "fr")
        converter.to_ogg_opus.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_requesting_ogg_converts_the_fetched_audio(self):
        service, client, converter, storage = _make_service()

        audio, content_type = await service.get_audio("bonjour", "fr", audio_format="ogg")

        assert audio == b"fake-ogg-bytes"
        assert content_type == "audio/ogg"
        converter.to_ogg_opus.assert_awaited_once_with(b"fake-mp3-bytes")

    @pytest.mark.asyncio
    async def test_requesting_mp3_explicitly_skips_conversion(self):
        service, client, converter, storage = _make_service()

        audio, content_type = await service.get_audio("bonjour", "fr", audio_format="mp3")

        assert audio == b"fake-mp3-bytes"
        assert content_type == "audio/mpeg"
        converter.to_ogg_opus.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_client_and_converter(self):
        service, client, converter, storage = _make_service(cached_audio=b"cached-bytes")

        audio, content_type = await service.get_audio("bonjour", "fr", audio_format="ogg")

        assert audio == b"cached-bytes"
        assert content_type == "audio/ogg"
        client.get_audio.assert_not_awaited()
        converter.to_ogg_opus.assert_not_awaited()
        storage.save.assert_not_awaited()

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
