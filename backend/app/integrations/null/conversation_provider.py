from app.shared.conversation import ConversationTurnResult

_CANNED_REPLY = "[stubbed conversation reply — integrations disabled]"


class NullConversationProvider:
    """No-op ConversationProvider: returns a canned turn without calling Gemini.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so the language
    conversation/roleplay endpoints run end-to-end deterministically.
    """

    @property
    def provider(self) -> str:
        return "null"

    @property
    def model(self) -> str:
        return "null"

    async def reply_audio(
        self,
        history: list[dict[str, str]],
        current_audio: bytes,
        mime_type: str,
        system: str,
    ) -> ConversationTurnResult:
        return ConversationTurnResult(
            transcript="[stubbed transcript]",
            reply=_CANNED_REPLY,
            tip=None,
            raw_response=_CANNED_REPLY,
            tokens_input=0,
            tokens_output=0,
            finish_reason="STOP",
        )

    async def reply_text(
        self,
        history: list[dict[str, str]],
        current_text: str,
        system: str,
    ) -> ConversationTurnResult:
        return ConversationTurnResult(
            transcript=current_text,
            reply=_CANNED_REPLY,
            tip=None,
            raw_response=_CANNED_REPLY,
            tokens_input=0,
            tokens_output=0,
            finish_reason="STOP",
        )
