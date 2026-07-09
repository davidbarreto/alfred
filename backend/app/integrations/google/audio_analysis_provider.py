from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from app.features.language.sessions.prompts import SHADOWING_ANALYSIS_PROMPT
from app.shared.audio import PronunciationAnalysis, PronunciationAnalysisResult

logger = logging.getLogger(__name__)


class GoogleAudioAnalysisProvider:
    """AudioAnalysisProvider implementation backed by Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self._model_name = model_name
        self._client = genai.Client(api_key=api_key)

    @property
    def provider(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._model_name

    async def analyze_pronunciation(
        self,
        audio: bytes,
        mime_type: str,
        text: str,
        translation: str | None,
        language_name: str,
    ) -> PronunciationAnalysisResult:
        prompt = SHADOWING_ANALYSIS_PROMPT.format(
            text=text, language_name=language_name, translation=translation or "",
        )
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=audio, mime_type=mime_type),
                prompt,
            ],
        )
        raw_response = response.text or ""
        usage = response.usage_metadata
        return PronunciationAnalysisResult(
            analysis=_parse_response(raw_response),
            raw_response=raw_response,
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
        )


def _parse_response(raw: str) -> PronunciationAnalysis:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    data = json.loads(text)
    return PronunciationAnalysis(
        transcription=data["transcription"],
        score=float(data["score"]),
        summary=data["summary"],
        strengths=list(data.get("strengths", [])),
        issues=list(data.get("issues", [])),
        tip=data.get("tip", ""),
    )
