from __future__ import annotations

import logging

from google import genai
from google.genai import types

from app.shared.audio import TranscriptionResult

logger = logging.getLogger(__name__)

_TRANSCRIBE_PROMPT = "Transcribe the speech in this audio verbatim. Return only the transcription text, with no extra commentary or formatting."


class GoogleTranscriptionProvider:
    """TranscriptionProvider implementation backed by Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self._model_name = model_name
        self._client = genai.Client(api_key=api_key)

    @property
    def provider(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._model_name

    async def transcribe(self, audio: bytes, mime_type: str, context: str | None = None) -> TranscriptionResult:
        prompt = f"{_TRANSCRIBE_PROMPT} {context}" if context else _TRANSCRIBE_PROMPT
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=audio, mime_type=mime_type),
                prompt,
            ],
        )
        usage = response.usage_metadata
        finish_reason = (
            str(response.candidates[0].finish_reason.name)
            if response.candidates and response.candidates[0].finish_reason
            else None
        )
        return TranscriptionResult(
            text=(response.text or "").strip(),
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
            finish_reason=finish_reason,
        )
