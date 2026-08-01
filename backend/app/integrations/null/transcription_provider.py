from app.shared.audio import TranscriptionResult

_CANNED_TEXT = "[stubbed transcription — integrations disabled]"


class NullTranscriptionProvider:
    """No-op TranscriptionProvider: returns canned text without calling Gemini.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so the
    transcription endpoint runs end-to-end deterministically.
    """

    @property
    def provider(self) -> str:
        return "null"

    @property
    def model(self) -> str:
        return "null"

    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionResult:
        return TranscriptionResult(text=_CANNED_TEXT, tokens_input=0, tokens_output=0, finish_reason="STOP")
