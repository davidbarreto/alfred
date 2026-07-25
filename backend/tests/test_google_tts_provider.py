import wave
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.google.tts_provider import GoogleTtsProvider


def _mock_response(pcm: bytes) -> MagicMock:
    resp = MagicMock()
    resp.candidates[0].content.parts[0].inline_data.data = pcm
    return resp


class TestProviderIdentity:

    def test_exposes_provider_and_model(self):
        provider = GoogleTtsProvider(api_key="test-key", model_name="gemini-2.5-flash-tts", voice_name="Enceladus")

        assert provider.provider == "google"
        assert provider.model == "gemini-2.5-flash-tts"


class TestGetAudio:

    @pytest.mark.asyncio
    async def test_calls_gemini_with_voice_config(self):
        with patch("app.integrations.google.tts_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_response(b"\x00\x01\x02\x03"))
            mock_client_cls.return_value = mock_client

            provider = GoogleTtsProvider(api_key="test-key", model_name="gemini-2.5-flash-tts", voice_name="Enceladus")
            await provider.get_audio("Bonjour", "fr")

        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash-tts"
        assert call_kwargs["contents"] == "Bonjour"
        speech_config = call_kwargs["config"].speech_config
        assert speech_config.voice_config.prebuilt_voice_config.voice_name == "Enceladus"
        assert call_kwargs["config"].response_modalities == ["AUDIO"]

    @pytest.mark.asyncio
    async def test_wraps_pcm_in_valid_wav_container(self):
        pcm = b"\x01\x02\x03\x04"
        with patch("app.integrations.google.tts_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_response(pcm))
            mock_client_cls.return_value = mock_client

            provider = GoogleTtsProvider(api_key="test-key", model_name="gemini-2.5-flash-tts", voice_name="Enceladus")
            result = await provider.get_audio("hello", "en")

        with wave.open(BytesIO(result), "rb") as wav_file:
            assert wav_file.getnchannels() == 1
            assert wav_file.getsampwidth() == 2
            assert wav_file.getframerate() == 24000
            assert wav_file.readframes(wav_file.getnframes()) == pcm
