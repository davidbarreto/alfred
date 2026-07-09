from __future__ import annotations

from typing import Protocol


class PronunciationProvider(Protocol):
    """Async interface for fetching spoken-word pronunciation audio.

    Swap the implementation (Google Translate TTS, Forvo, …) without
    touching the chunks service layer.
    """

    async def get_audio(self, text: str, lang: str) -> bytes: ...
