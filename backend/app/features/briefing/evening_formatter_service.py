from __future__ import annotations

import logging
import time as time_module
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.prompts import EVENING_DIGEST_SYSTEM_PROMPT
from app.features.briefing.repository import BriefingRepository
from app.features.briefing.schemas import EveningDigest, FormattedBriefing
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_BRIEFING_TYPE = "evening"
_HEADER = "🌙 Evening Digest"


def _build_context(digest: EveningDigest) -> str:
    lines = [f"Date: {digest.date.strftime('%A, %d %B %Y')}"]

    lines.append("")
    lines.append(f"Completed today ({len(digest.wins)}):")
    if digest.wins:
        for win in digest.wins:
            lines.append(f"  {win.title}")
    else:
        lines.append("  Nothing marked done today.")

    lines.append("")
    lines.append(f"Open tasks ({len(digest.tasks)}):")
    if digest.tasks:
        for task in digest.tasks:
            deadline_str = task.deadline.strftime("%a %d %b %H:%M") if task.deadline else "no deadline"
            overdue = " [OVERDUE]" if task.is_overdue else ""
            tags = f" [{', '.join(task.tags)}]" if task.tags else ""
            lines.append(f"  {task.title} | {task.priority} priority | due {deadline_str}{overdue}{tags}")
    else:
        lines.append("  No open tasks.")

    lines.append("")
    lines.append(f"Tomorrow's events ({len(digest.tomorrow_events)}):")
    if digest.tomorrow_events:
        for event in digest.tomorrow_events:
            time_str = event.start_time if event.all_day else f"{event.start_time} - {event.end_time}"
            location = f" at {event.location}" if event.location else ""
            lines.append(f"  {event.title} | {time_str}{location}")
    else:
        lines.append("  No events tomorrow.")

    if digest.notes:
        lines.append("")
        lines.append("Recent notes (context only, not actionable):")
        for note in digest.notes:
            lines.append(f"  {note.title}")

    return "\n".join(lines)


class EveningDigestFormatterService:
    def __init__(self, llm_provider: LlmProvider, session: AsyncSession) -> None:
        self._llm_provider = llm_provider
        self._session = session
        self._repo = BriefingRepository(session)

    async def get_saved(self, digest_date: date | None = None) -> FormattedBriefing | None:
        if digest_date is None:
            digest_date = local_now().date()
        saved = await self._repo.get_briefing_by_date(digest_date, _BRIEFING_TYPE)
        if saved is None:
            logger.debug("Saved evening digest: date=%s not found", digest_date)
            return None
        logger.info("Reusing saved evening digest: date=%s", digest_date)
        return FormattedBriefing(date=saved.date, text=saved.text)

    async def format(self, digest: EveningDigest) -> FormattedBriefing:
        context = _build_context(digest)
        messages = [{"role": "user", "content": context}]

        t0 = time_module.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=EVENING_DIGEST_SYSTEM_PROMPT)
        latency_ms = int((time_module.monotonic() - t0) * 1000)

        text = f"{_HEADER}\n\n{llm_response.text.strip()}"

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="evening_digest",
            prompt=messages,
            response=text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_ms=latency_ms,
        )
        await self._repo.upsert_briefing(digest.date, _BRIEFING_TYPE, text)
        await self._session.commit()
        logger.info("Evening digest formatted and saved: date=%s", digest.date)

        return FormattedBriefing(date=digest.date, text=text)
