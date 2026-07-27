from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TtsAudioResult:
    """Synthesized audio plus optional model call metadata, for llm_calls logging.
    tokens_input/tokens_output/finish_reason stay None for providers that aren't
    LLM-backed (e.g. Google Translate TTS has no such concepts)."""

    audio: bytes
    tokens_input: int | None = None
    tokens_output: int | None = None
    finish_reason: str | None = None


class PronunciationProvider(Protocol):
    """Async interface for fetching spoken-word pronunciation audio.

    Swap the implementation (Google Translate TTS, Forvo, …) without
    touching the chunks service layer.
    """

    async def get_audio(self, text: str, lang: str) -> TtsAudioResult: ...
