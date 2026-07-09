from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.google.transcription_provider import GoogleTranscriptionProvider


def _mock_response(text: str, tokens_input: int = 100, tokens_output: int = 50) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata.prompt_token_count = tokens_input
    resp.usage_metadata.candidates_token_count = tokens_output
    return resp


class TestProviderIdentity:

    def test_exposes_provider_and_model(self):
        provider = GoogleTranscriptionProvider(api_key="test-key", model_name="gemini-2.5-flash")

        assert provider.provider == "google"
        assert provider.model == "gemini-2.5-flash"


class TestTranscribe:

    @pytest.mark.asyncio
    async def test_calls_gemini_with_audio_and_returns_text(self):
        with patch("app.integrations.google.transcription_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_response("  hello there  "))
            mock_client_cls.return_value = mock_client

            provider = GoogleTranscriptionProvider(api_key="test-key", model_name="gemini-2.5-flash")
            result = await provider.transcribe(audio=b"fake-audio", mime_type="audio/ogg")

        assert result.text == "hello there"
        assert result.tokens_input == 100
        assert result.tokens_output == 50
        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_text(self):
        with patch("app.integrations.google.transcription_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            resp = MagicMock()
            resp.text = None
            resp.usage_metadata = None
            mock_client.aio.models.generate_content = AsyncMock(return_value=resp)
            mock_client_cls.return_value = mock_client

            provider = GoogleTranscriptionProvider(api_key="test-key", model_name="gemini-2.5-flash")
            result = await provider.transcribe(audio=b"fake-audio", mime_type="audio/ogg")

        assert result.text == ""
        assert result.tokens_input is None
        assert result.tokens_output is None
