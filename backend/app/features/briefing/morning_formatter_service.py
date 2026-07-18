from __future__ import annotations

import logging
import time as time_module
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.prompts import MORNING_BRIEFING_SYSTEM_PROMPT
from app.features.briefing.repository import BriefingRepository
from app.features.briefing.schemas import FormattedBriefing, MorningBriefing
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_BRIEFING_TYPE = "morning"
_HEADER = "☀️ Morning Briefing"


def _build_context(briefing: MorningBriefing) -> str:
    lines = [f"Date: {briefing.date.strftime('%A, %d %B %Y')}"]

    today_tasks = [t for t in briefing.tasks if t.is_today or t.is_overdue]
    upcoming_tasks = [t for t in briefing.tasks if not t.is_today and not t.is_overdue]

    lines.append("")
    lines.append(f"Tasks due today or overdue ({len(today_tasks)}):")
    if today_tasks:
        for task in today_tasks:
            deadline_str = task.deadline.strftime("%d %b") if task.deadline else "no deadline"
            overdue = " [OVERDUE]" if task.is_overdue else ""
            tags = f" [{', '.join(task.tags)}]" if task.tags else ""
            lines.append(f"  {task.title} | {task.priority} priority | due {deadline_str}{overdue}{tags}")
    else:
        lines.append("  No tasks due today.")

    if upcoming_tasks:
        lines.append("")
        lines.append(f"Tasks due in the next {briefing.lookahead_days} days ({len(upcoming_tasks)}):")
        for task in upcoming_tasks:
            deadline_str = task.deadline.strftime("%a %d %b") if task.deadline else "no deadline"
            tags = f" [{', '.join(task.tags)}]" if task.tags else ""
            lines.append(f"  {task.title} | {task.priority} priority | due {deadline_str}{tags}")

    today_events = [e for e in briefing.events if e.is_today]
    upcoming_events = [e for e in briefing.events if not e.is_today]

    lines.append("")
    lines.append(f"Events today ({len(today_events)}):")
    if today_events:
        for event in today_events:
            time_str = event.start_time if event.all_day else f"{event.start_time} - {event.end_time}"
            location = f" at {event.location}" if event.location else ""
            lines.append(f"  {event.title} | {time_str}{location}")
    else:
        lines.append("  No events today.")

    if upcoming_events:
        lines.append("")
        lines.append(f"Events in the next {briefing.lookahead_days} days ({len(upcoming_events)}):")
        for event in upcoming_events:
            day_str = event.date.strftime("%a %d %b")
            time_str = event.start_time if event.all_day else f"{event.start_time} - {event.end_time}"
            location = f" at {event.location}" if event.location else ""
            lines.append(f"  {event.title} | {day_str}, {time_str}{location}")

    w = briefing.weather
    lines.append("")
    lines.append("Weather in Porto:")
    if w is None:
        lines.append("  Unavailable")
    else:
        lines.append(
            f"  {w.description}, {w.temperature_min_c}C - {w.temperature_max_c}C"
            f" (feels like up to {w.feels_like_max_c}C)"
        )
        lines.append(f"  Rain probability: {w.precipitation_probability}%, Wind: {w.wind_speed_max_kmh} km/h")
        if w.advice:
            lines.append(f"  Advice: {', '.join(w.advice)}")

    if briefing.holidays:
        lines.append("")
        lines.append("Upcoming holidays:")
        for h in briefing.holidays:
            if h.days_until == 0:
                lines.append(f"  {h.local_name} ({h.country}) — today!")
            elif h.days_until == 1:
                lines.append(f"  {h.local_name} ({h.country}) — tomorrow ({h.date.strftime('%d %b')})")
            else:
                lines.append(f"  {h.local_name} ({h.country}) — in {h.days_until} days ({h.date.strftime('%d %b')})")

    if briefing.birthdays:
        lines.append("")
        lines.append("Birthdays:")
        for b in briefing.birthdays:
            if b.days_until == 0:
                lines.append(f"  {b.name} — today!")
            elif b.days_until == 1:
                lines.append(f"  {b.name} — tomorrow ({b.date.strftime('%d %b')})")
            else:
                lines.append(f"  {b.name} — in {b.days_until} days ({b.date.strftime('%d %b')})")

    if briefing.shopping:
        lines.append("")
        lines.append(f"Shopping list — pending items ({len(briefing.shopping)}):")
        for item in briefing.shopping:
            qty = ""
            if item.quantity is not None:
                amount = f"{item.quantity:g}"
                qty = f" x{amount} {item.unit}" if item.unit else f" x{amount}"
            store = f" at {item.store}" if item.store else ""
            lines.append(f"  {item.name}{qty} | {item.category} | {item.priority}{store}")

    active_language = [t for t in briefing.language if t.due_count > 0 or t.completed_today > 0]
    if active_language:
        lines.append("")
        lines.append("Language practice:")
        for lang in active_language:
            # due_count is the raw SRS backlog and can be huge (hundreds of cards);
            # cap what's shown at daily_quota so the briefing reports today's goal,
            # not the full backlog.
            remaining = max(0, min(lang.due_count, lang.daily_quota) - lang.completed_today)
            if lang.quota_met:
                lines.append(f"  {lang.name}: quota met ({lang.completed_today}/{lang.daily_quota} reviews done)")
            elif lang.completed_today > 0:
                lines.append(
                    f"  {lang.name}: {lang.completed_today}/{lang.daily_quota} done, "
                    f"{remaining} more to hit today's goal"
                )
            else:
                lines.append(f"  {lang.name}: {remaining} review(s) to hit today's goal")

    return "\n".join(lines)


class MorningBriefingFormatterService:
    def __init__(self, llm_provider: LlmProvider, session: AsyncSession) -> None:
        self._llm_provider = llm_provider
        self._session = session
        self._repo = BriefingRepository(session)

    async def get_saved(self, briefing_date: date | None = None) -> FormattedBriefing | None:
        if briefing_date is None:
            briefing_date = local_now().date()
        saved = await self._repo.get_briefing_by_date(briefing_date, _BRIEFING_TYPE)
        if saved is None:
            logger.debug("Saved briefing: date=%s not found", briefing_date)
            return None
        logger.info("Reusing saved briefing: date=%s", briefing_date)
        return FormattedBriefing(date=saved.date, text=saved.text)

    async def format(self, briefing: MorningBriefing) -> FormattedBriefing:
        context = _build_context(briefing)
        messages = [{"role": "user", "content": context}]

        t0 = time_module.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=MORNING_BRIEFING_SYSTEM_PROMPT)
        latency_ms = int((time_module.monotonic() - t0) * 1000)

        text = f"{_HEADER}\n\n{llm_response.text.strip()}"

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="morning_briefing",
            prompt=messages,
            response=text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_ms=latency_ms,
        )
        await self._repo.upsert_briefing(briefing.date, _BRIEFING_TYPE, text)
        await self._session.commit()
        logger.info("Briefing formatted and saved: date=%s", briefing.date)

        return FormattedBriefing(date=briefing.date, text=text)
