import pytest
from unittest.mock import AsyncMock

from app.features.language.chunks.pronunciation_service import PronunciationService


def _make_service(**kwargs):
    client = kwargs.get("client") or AsyncMock()
    converter = kwargs.get("converter") or AsyncMock()
    client.get_audio.return_value = kwargs.get("fetched_audio", b"fake-mp3-bytes")
    converter.to_ogg_opus.return_value = kwargs.get("converted_audio", b"fake-ogg-bytes")
    return PronunciationService(client, converter), client, converter


class TestGetAudio:

    @pytest.mark.asyncio
    async def test_defaults_to_mp3_without_conversion(self):
        service, client, converter = _make_service()

        audio, content_type = await service.get_audio("bonjour", "fr")

        assert audio == b"fake-mp3-bytes"
        assert content_type == "audio/mpeg"
        client.get_audio.assert_awaited_once_with("bonjour", "fr")
        converter.to_ogg_opus.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_requesting_ogg_converts_the_fetched_audio(self):
        service, client, converter = _make_service()

        audio, content_type = await service.get_audio("bonjour", "fr", audio_format="ogg")

        assert audio == b"fake-ogg-bytes"
        assert content_type == "audio/ogg"
        converter.to_ogg_opus.assert_awaited_once_with(b"fake-mp3-bytes")

    @pytest.mark.asyncio
    async def test_requesting_mp3_explicitly_skips_conversion(self):
        service, client, converter = _make_service()

        audio, content_type = await service.get_audio("bonjour", "fr", audio_format="mp3")

        assert audio == b"fake-mp3-bytes"
        assert content_type == "audio/mpeg"
        converter.to_ogg_opus.assert_not_awaited()
