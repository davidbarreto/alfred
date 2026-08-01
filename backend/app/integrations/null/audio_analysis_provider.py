from app.shared.audio import PronunciationAnalysis, PronunciationAnalysisResult

_CANNED_TEXT = "[stubbed pronunciation analysis — integrations disabled]"


class NullAudioAnalysisProvider:
    """No-op AudioAnalysisProvider: returns a canned analysis without calling Gemini.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so the shadowing
    endpoints run end-to-end deterministically.
    """

    @property
    def provider(self) -> str:
        return "null"

    @property
    def model(self) -> str:
        return "null"

    async def analyze_pronunciation(
        self,
        audio: bytes,
        mime_type: str,
        text: str,
        translation: str | None,
        language_name: str,
    ) -> PronunciationAnalysisResult:
        return PronunciationAnalysisResult(
            analysis=PronunciationAnalysis(
                transcription=text,
                score=0.0,
                summary=_CANNED_TEXT,
                strengths=[],
                issues=[],
                tip=_CANNED_TEXT,
            ),
            raw_response=_CANNED_TEXT,
            tokens_input=0,
            tokens_output=0,
            finish_reason="STOP",
        )
