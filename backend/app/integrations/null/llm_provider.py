from typing import AsyncGenerator

from app.shared.llm import LlmResponse, StreamMeta

_CANNED_TEXT = "[stubbed LLM response — integrations disabled]"


class NullLlmProvider:
    """No-op LlmProvider: returns a canned response without calling out to any provider.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so chat, memory
    extraction, briefing formatting, etc. can run end-to-end deterministically.
    """

    @property
    def provider(self) -> str:
        return "null"

    @property
    def model(self) -> str:
        return "null"

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> LlmResponse:
        return LlmResponse(text=_CANNED_TEXT, tokens_input=0, tokens_output=0, finish_reason="STOP")

    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        meta: StreamMeta | None = None,
    ) -> AsyncGenerator[str, None]:
        if meta is not None:
            meta.set_finish_reason("STOP")
        yield _CANNED_TEXT
