from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ConversationTurnResult:
    """One conversational turn: what the user said, how Alfred replied, an optional
    pronunciation/grammar tip, and how the reply should be spoken — plus the raw LLM
    call metadata, for llm_calls logging.

    `transcript` is the AI's transcription for an audio turn, and simply the user's
    own text for a text turn."""

    transcript: str
    reply: str
    tip: str | None
    raw_response: str
    tokens_input: int | None
    tokens_output: int | None
    tone: str | None = None


class ConversationProvider(Protocol):
    """Async interface for a multi-turn conversation with an AI, in either modality.

    Only the newest turn carries raw audio; `history` always carries prior turns as
    plain text so payload size stays bounded across a long conversation. Audio turns
    go to the model natively (no separate speech-to-text step) so it can judge
    pronunciation. Swap the implementation (Google Gemini, …) without touching the
    conversation service layer.
    """

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def reply_audio(
        self,
        history: list[dict[str, str]],
        current_audio: bytes,
        mime_type: str,
        system: str,
    ) -> ConversationTurnResult: ...

    async def reply_text(
        self,
        history: list[dict[str, str]],
        current_text: str,
        system: str,
    ) -> ConversationTurnResult: ...
