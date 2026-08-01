import pytest

from app.integrations.null.audio_analysis_provider import NullAudioAnalysisProvider
from app.integrations.null.conversation_provider import NullConversationProvider
from app.integrations.null.pronunciation_provider import NullPronunciationProvider
from app.integrations.null.transcription_provider import NullTranscriptionProvider


class TestNullPronunciationProvider:

    @pytest.mark.asyncio
    async def test_get_audio_returns_empty_audio(self):
        provider = NullPronunciationProvider()

        result = await provider.get_audio("bonjour", "fr")

        assert result.audio == b""
        assert result.finish_reason == "STOP"


class TestNullConversationProvider:

    @pytest.mark.asyncio
    async def test_reply_text_echoes_transcript_and_returns_canned_reply(self):
        provider = NullConversationProvider()

        result = await provider.reply_text([], "hello", system="sys")

        assert result.transcript == "hello"
        assert result.reply
        assert result.finish_reason == "STOP"

    @pytest.mark.asyncio
    async def test_reply_audio_returns_canned_reply(self):
        provider = NullConversationProvider()

        result = await provider.reply_audio([], b"audio-bytes", "audio/ogg", system="sys")

        assert result.reply
        assert result.finish_reason == "STOP"

    def test_exposes_provider_and_model_name(self):
        provider = NullConversationProvider()

        assert provider.provider == "null"
        assert provider.model == "null"


class TestNullAudioAnalysisProvider:

    @pytest.mark.asyncio
    async def test_analyze_pronunciation_echoes_text_as_transcription(self):
        provider = NullAudioAnalysisProvider()

        result = await provider.analyze_pronunciation(
            audio=b"audio-bytes", mime_type="audio/ogg", text="bonjour", translation="hello", language_name="French"
        )

        assert result.analysis.transcription == "bonjour"
        assert result.finish_reason == "STOP"


class TestNullTranscriptionProvider:

    @pytest.mark.asyncio
    async def test_transcribe_returns_canned_text(self):
        provider = NullTranscriptionProvider()

        result = await provider.transcribe(b"audio-bytes", "audio/ogg")

        assert result.text
        assert result.finish_reason == "STOP"
