import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.google.audio_analysis_provider import GoogleAudioAnalysisProvider, _parse_response
from app.shared.audio import PronunciationAnalysis

_VALID_JSON = json.dumps({
    "transcription": "bonjour",
    "score": 85,
    "summary": "Clear and natural.",
    "strengths": ["Good vowel sounds"],
    "issues": ["Slight stress on the wrong syllable"],
    "tip": "Stress the second syllable.",
})


def _mock_response(text: str, tokens_input: int = 100, tokens_output: int = 50) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata.prompt_token_count = tokens_input
    resp.usage_metadata.candidates_token_count = tokens_output
    return resp


class TestParseResponse:

    def test_parses_plain_json(self):
        result = _parse_response(_VALID_JSON)

        assert result == PronunciationAnalysis(
            transcription="bonjour", score=85.0, summary="Clear and natural.",
            strengths=["Good vowel sounds"], issues=["Slight stress on the wrong syllable"],
            tip="Stress the second syllable.",
        )

    def test_strips_markdown_fences(self):
        fenced = f"```json\n{_VALID_JSON}\n```"

        result = _parse_response(fenced)

        assert result.score == 85.0

    def test_raises_on_unparseable_response(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_response("not json at all")


class TestProviderIdentity:

    def test_exposes_provider_and_model(self):
        provider = GoogleAudioAnalysisProvider(api_key="test-key", model_name="gemini-2.5-flash")

        assert provider.provider == "google"
        assert provider.model == "gemini-2.5-flash"


class TestAnalyzePronunciation:

    @pytest.mark.asyncio
    async def test_calls_gemini_with_audio_and_prompt(self):
        with patch("app.integrations.google.audio_analysis_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_response(_VALID_JSON))
            mock_client_cls.return_value = mock_client

            provider = GoogleAudioAnalysisProvider(api_key="test-key", model_name="gemini-2.5-flash")
            result = await provider.analyze_pronunciation(
                audio=b"fake-audio", mime_type="audio/ogg",
                text="bonjour", translation="hello", language_name="French",
            )

        assert result.analysis.transcription == "bonjour"
        assert result.analysis.score == 85.0
        assert result.raw_response == _VALID_JSON
        assert result.tokens_input == 100
        assert result.tokens_output == 50
        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash"
        prompt = call_kwargs["contents"][1]
        assert "bonjour" in prompt
        assert "French" in prompt
