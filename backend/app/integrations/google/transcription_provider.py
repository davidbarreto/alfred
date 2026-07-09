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

    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionResult:
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=audio, mime_type=mime_type),
                _TRANSCRIBE_PROMPT,
            ],
        )
        usage = response.usage_metadata
        return TranscriptionResult(
            text=(response.text or "").strip(),
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
        )
