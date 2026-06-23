from __future__ import annotations

import logging
import time
from datetime import datetime

from app.db.session import async_session
from app.features.core.messages.schemas import MessageFilters
from app.features.core.messages.service import MessageService
from app.features.core.sessions.repository import SessionRepository
from app.features.core.prompts import SESSION_SUMMARY_PROMPT
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_SUMMARY_LIMIT = 5


class SessionSummaryService:
    def __init__(self, llm_provider: LlmProvider) -> None:
        self._llm_provider = llm_provider

    async def summarise_and_save(
        self, source: str, external_id: str, new_session_id: int
    ) -> None:
        try:
            await self._do_summarise(source, external_id, new_session_id)
        except Exception:
            logger.exception(
                "Session summarisation failed source=%s external_id=%s", source, external_id
            )

    async def _do_summarise(
        self, source: str, external_id: str, new_session_id: int
    ) -> None:
        async with async_session() as session:
            repo = SessionRepository(session)
            previous = await repo.get_previous(source, external_id, exclude_id=new_session_id)
            if previous is None:
                return
            if previous.summary is not None:
                return  # already summarised

            messages = await MessageService(session).list(
                MessageFilters(session_id=previous.id)
            )
            if not messages:
                return

            formatted = "\n".join(
                f"{'User' if m.role == 'user' else 'Alfred'}: {m.content}"
                for m in messages
            )
            prompt_messages = [{"role": "user", "content": SESSION_SUMMARY_PROMPT.format(messages=formatted)}]
            t0 = time.monotonic()
            llm_response = await self._llm_provider.complete(prompt_messages)
            latency_ms = int((time.monotonic() - t0) * 1000)
            summary = llm_response.text.strip()
            await repo.update_summary(previous.id, summary)
            await create_llm_call(
                session,
                provider=self._llm_provider.provider,
                model=self._llm_provider.model,
                feature="session_summary",
                prompt=prompt_messages,
                response=summary,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                latency_ms=latency_ms,
            )
            logger.info("Session %d summarised (%d messages)", previous.id, len(messages))

    async def get_recent_summaries(
        self, session_id: int, limit: int = _SUMMARY_LIMIT
    ) -> list[tuple[datetime, str]]:
        async with async_session() as session:
            repo = SessionRepository(session)
            current = await repo.get(session_id)
            if current is None or not current.source or not current.external_id:
                return []
            sessions = await repo.get_recent_with_summaries(
                source=current.source,
                external_id=current.external_id,
                exclude_id=session_id,
                limit=limit,
            )
            return [
                (s.last_interaction_at, s.summary)
                for s in sessions
                if s.summary
            ]
