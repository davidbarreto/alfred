from unittest.mock import AsyncMock, patch

import pytest

from app.features.core.transcription.service import TranscriptionService
from app.shared.audio import TranscriptionResult


def _make_service(**kwargs):
    session = kwargs.get("session") or AsyncMock()
    provider = kwargs.get("provider") or AsyncMock()
    provider.provider = "google"
    provider.model = "gemini-2.5-flash"
    provider.transcribe.return_value = kwargs.get(
        "result", TranscriptionResult(text="hello there", tokens_input=100, tokens_output=50),
    )
    service = TranscriptionService(provider=provider, session=session)
    return service, session, provider


class TestTranscribe:

    @pytest.mark.asyncio
    async def test_transcribes_and_logs_llm_call(self):
        service, session, provider = _make_service()

        with patch("app.features.core.transcription.service.create_llm_call", AsyncMock()) as mock_log:
            result = await service.transcribe(b"raw-audio", "audio/ogg")

        provider.transcribe.assert_awaited_once_with(b"raw-audio", "audio/ogg")
        assert result.text == "hello there"

        mock_log.assert_awaited_once()
        log_call = mock_log.call_args
        assert log_call.args[0] is session
        assert log_call.kwargs["provider"] == "google"
        assert log_call.kwargs["model"] == "gemini-2.5-flash"
        assert log_call.kwargs["feature"] == "transcription"
        assert log_call.kwargs["response"] == "hello there"
        assert log_call.kwargs["tokens_input"] == 100
        assert log_call.kwargs["tokens_output"] == 50
        assert log_call.kwargs["latency_ms"] >= 0
