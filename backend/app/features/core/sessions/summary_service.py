from __future__ import annotations

import logging
from datetime import datetime

from app.db.session import async_session
from app.features.core.messages.schemas import MessageFilters
from app.features.core.messages.service import MessageService
from app.features.core.sessions.repository import SessionRepository
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_SUMMARY_LIMIT = 3

_SUMMARY_PROMPT = """\
Summarise this conversation in 3-5 sentences for an AI assistant's long-term memory.
Include: main topics discussed, decisions or actions taken, important facts the user shared, \
and any open questions or follow-ups.
Be concise — this will be injected into future conversation prompts.

Conversation:
{messages}"""


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
            llm_response = await self._llm_provider.complete(
                [{"role": "user", "content": _SUMMARY_PROMPT.format(messages=formatted)}]
            )
            summary = llm_response.text.strip()
            await repo.update_summary(previous.id, summary)
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
