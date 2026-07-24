from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from app.shared.audio import AudioConversationResult

logger = logging.getLogger(__name__)


class GoogleConversationProvider:
    """AudioConversationProvider implementation backed by Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self._model_name = model_name
        self._client = genai.Client(api_key=api_key)

    @property
    def provider(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._model_name

    def _build_contents(
        self, history: list[dict[str, str]], current_audio: bytes, mime_type: str
    ) -> list[types.Content]:
        # Sanitize history to enforce strict user/model role alternation that Gemini
        # requires (same approach as GoogleLlmProvider._build_contents). The current
        # turn always carries raw audio, appended after the sanitized text history.
        sanitized: list[dict[str, str]] = []
        for msg in history:
            if sanitized and sanitized[-1]["role"] == msg["role"]:
                sanitized[-1] = {
                    "role": msg["role"],
                    "content": sanitized[-1]["content"] + "\n" + msg["content"],
                }
            else:
                sanitized.append(msg)

        if sanitized and sanitized[-1]["role"] == "user":
            sanitized.append({"role": "assistant", "content": "(handled)"})

        contents = [
            types.Content(
                role="model" if msg["role"] == "assistant" else "user",
                parts=[types.Part(text=msg["content"])],
            )
            for msg in sanitized
        ]
        contents.append(
            types.Content(role="user", parts=[types.Part.from_bytes(data=current_audio, mime_type=mime_type)])
        )
        return contents

    async def reply(
        self,
        history: list[dict[str, str]],
        current_audio: bytes,
        mime_type: str,
        system: str,
    ) -> AudioConversationResult:
        contents = self._build_contents(history, current_audio, mime_type)
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        raw_response = response.text or ""
        usage = response.usage_metadata
        parsed = _parse_response(raw_response)
        return AudioConversationResult(
            transcript=parsed["transcript"],
            reply=parsed["reply"],
            tip=parsed.get("tip") or None,
            raw_response=raw_response,
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
        )


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)
