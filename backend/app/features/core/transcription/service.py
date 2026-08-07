import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.commands.registry import NL_TRIGGER_INDEX
from app.features.core.transcription.schemas import TranscriptionRead
from app.features.organizer.contacts.repository import ContactRepository
from app.features.organizer.contacts.schemas import ContactFilters
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import TranscriptionProvider

logger = logging.getLogger(__name__)

_COMMAND_PHRASES = ", ".join(sorted({trigger for trigger, _ in NL_TRIGGER_INDEX}))


class TranscriptionService:

    def __init__(self, provider: TranscriptionProvider, session: AsyncSession) -> None:
        self._provider = provider
        self._session = session

    async def _build_context(self) -> str:
        contacts = await ContactRepository(self._session).get_contacts(
            ContactFilters(
                limit=1000,
                offset=0,
                name=None,
                email=None,
                letter=None,
                has_birthday=None,
                relationship="family",
            )
        )
        hints = [f"Known commands the speaker may start with: {_COMMAND_PHRASES}."]
        if contacts:
            names = ", ".join(sorted(c.name for c in contacts))
            hints.append(f"Family member names that may be mentioned: {names}.")
        return " ".join(hints)

    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionRead:
        t0 = time.monotonic()
        context = await self._build_context()
        result = await self._provider.transcribe(audio, mime_type, context=context)
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._provider.provider,
            model=self._provider.model,
            feature="transcription",
            prompt=[{"role": "user", "content": "Transcribe audio"}],
            response=result.text,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            finish_reason=result.finish_reason,
            latency_ms=latency_ms,
            is_audio=True,
        )
        logger.info("Audio transcribed: chars=%d latency_ms=%d", len(result.text), latency_ms)
        return TranscriptionRead(text=result.text)
