from app.shared.pronunciation import TtsAudioResult


class NullPronunciationProvider:
    """No-op PronunciationProvider: returns empty audio without calling out.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so word-pronunciation
    and conversation-reply TTS endpoints return a well-formed (silent) response
    instead of crashing without real Gemini/Google Translate credentials.
    """

    async def get_audio(self, text: str, lang: str) -> TtsAudioResult:
        return TtsAudioResult(audio=b"", tokens_input=0, tokens_output=0, finish_reason="STOP")
