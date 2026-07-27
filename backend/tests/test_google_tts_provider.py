import wave
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.google.tts_provider import GoogleTtsProvider, TtsSynthesisError


def _mock_finish_reason(name: str) -> MagicMock:
    reason = MagicMock()
    reason.name = name
    return reason


def _mock_response(pcm: bytes, tokens_input: int = 10, tokens_output: int = 5) -> MagicMock:
    resp = MagicMock()
    resp.candidates[0].content.parts[0].inline_data.data = pcm
    resp.candidates[0].finish_reason = _mock_finish_reason("STOP")
    resp.usage_metadata.prompt_token_count = tokens_input
    resp.usage_metadata.candidates_token_count = tokens_output
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
    async def test_raises_clear_error_when_candidate_content_is_empty(self):
        with patch("app.integrations.google.tts_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            resp = MagicMock()
            resp.candidates[0].content = None
            resp.candidates[0].finish_reason = _mock_finish_reason("SAFETY")
            mock_client.aio.models.generate_content = AsyncMock(return_value=resp)
            mock_client_cls.return_value = mock_client

            provider = GoogleTtsProvider(api_key="test-key", model_name="gemini-2.5-flash-tts", voice_name="Enceladus")
            with pytest.raises(TtsSynthesisError, match="no audio content") as exc_info:
                await provider.get_audio("some text", "fr")

        assert exc_info.value.finish_reason == "SAFETY"

    @pytest.mark.asyncio
    async def test_raises_clear_error_when_no_candidates(self):
        with patch("app.integrations.google.tts_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            resp = MagicMock()
            resp.candidates = []
            mock_client.aio.models.generate_content = AsyncMock(return_value=resp)
            mock_client_cls.return_value = mock_client

            provider = GoogleTtsProvider(api_key="test-key", model_name="gemini-2.5-flash-tts", voice_name="Enceladus")
            with pytest.raises(RuntimeError, match="no audio content"):
                await provider.get_audio("some text", "fr")

    @pytest.mark.asyncio
    async def test_wraps_pcm_in_valid_wav_container(self):
        pcm = b"\x01\x02\x03\x04"
        with patch("app.integrations.google.tts_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_response(pcm))
            mock_client_cls.return_value = mock_client

            provider = GoogleTtsProvider(api_key="test-key", model_name="gemini-2.5-flash-tts", voice_name="Enceladus")
            result = await provider.get_audio("hello", "en")

        with wave.open(BytesIO(result.audio), "rb") as wav_file:
            assert wav_file.getnchannels() == 1
            assert wav_file.getsampwidth() == 2
            assert wav_file.getframerate() == 24000
            assert wav_file.readframes(wav_file.getnframes()) == pcm

    @pytest.mark.asyncio
    async def test_returns_tokens_and_finish_reason_on_success(self):
        with patch("app.integrations.google.tts_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=_mock_response(b"\x01\x02", tokens_input=12, tokens_output=7)
            )
            mock_client_cls.return_value = mock_client

            provider = GoogleTtsProvider(api_key="test-key", model_name="gemini-2.5-flash-tts", voice_name="Enceladus")
            result = await provider.get_audio("hello", "en")

        assert result.tokens_input == 12
        assert result.tokens_output == 7
        assert result.finish_reason == "STOP"
