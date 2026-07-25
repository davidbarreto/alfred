from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from app.shared.conversation import ConversationTurnResult

logger = logging.getLogger(__name__)


class GoogleConversationProvider:
    """ConversationProvider implementation backed by Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self._model_name = model_name
        self._client = genai.Client(api_key=api_key)

    @property
    def provider(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._model_name

    def _build_contents(self, history: list[dict[str, str]], current: types.Part) -> list[types.Content]:
        # Sanitize history to enforce strict user/model role alternation that Gemini
        # requires (same approach as GoogleLlmProvider._build_contents). The current
        # turn is appended after the sanitized text history, carrying either raw audio
        # or plain text depending on the modality.
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
        contents.append(types.Content(role="user", parts=[current]))
        return contents

    async def _generate(
        self, history: list[dict[str, str]], current: types.Part, system: str, fallback_transcript: str | None
    ) -> ConversationTurnResult:
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=self._build_contents(history, current),
            config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json"),
        )
        raw_response = response.text or ""
        usage = response.usage_metadata
        parsed = _parse_response(raw_response)
        return ConversationTurnResult(
            # A text turn needs no transcription — the user's own words are the transcript.
            transcript=fallback_transcript if fallback_transcript is not None else parsed["transcript"],
            reply=parsed["reply"],
            tip=parsed.get("tip") or None,
            raw_response=raw_response,
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
            tone=parsed.get("tone") or None,
        )

    async def reply_audio(
        self,
        history: list[dict[str, str]],
        current_audio: bytes,
        mime_type: str,
        system: str,
    ) -> ConversationTurnResult:
        current = types.Part.from_bytes(data=current_audio, mime_type=mime_type)
        return await self._generate(history, current, system, fallback_transcript=None)

    async def reply_text(
        self,
        history: list[dict[str, str]],
        current_text: str,
        system: str,
    ) -> ConversationTurnResult:
        return await self._generate(
            history, types.Part(text=current_text), system, fallback_transcript=current_text
        )


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("GoogleConversationProvider: non-JSON response: %r", raw[:500])
        raise
