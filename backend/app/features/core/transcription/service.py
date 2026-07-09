import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.transcription.schemas import TranscriptionRead
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import TranscriptionProvider

logger = logging.getLogger(__name__)


class TranscriptionService:

    def __init__(self, provider: TranscriptionProvider, session: AsyncSession) -> None:
        self._provider = provider
        self._session = session

    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionRead:
        t0 = time.monotonic()
        result = await self._provider.transcribe(audio, mime_type)
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
            latency_ms=latency_ms,
        )
        logger.info("Audio transcribed: chars=%d latency_ms=%d", len(result.text), latency_ms)
        return TranscriptionRead(text=result.text)
