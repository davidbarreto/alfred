from __future__ import annotations

import logging
import time as time_module

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.prompts import MORNING_BRIEFING_SYSTEM_PROMPT
from app.features.briefing.schemas import FormattedBriefing, MorningBriefing
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


def _build_context(briefing: MorningBriefing) -> str:
    lines = [f"Date: {briefing.date.strftime('%A, %d %B %Y')}"]

    lines.append("")
    lines.append(f"Tasks ({len(briefing.tasks)}):")
    if briefing.tasks:
        for task in briefing.tasks:
            deadline_str = task.deadline.strftime("%d %b") if task.deadline else "no deadline"
            overdue = " [OVERDUE]" if task.is_overdue else ""
            tags = f" [{', '.join(task.tags)}]" if task.tags else ""
            lines.append(f"  {task.title} | {task.priority} priority | due {deadline_str}{overdue}{tags}")
    else:
        lines.append("  No tasks due today.")

    lines.append("")
    lines.append(f"Events ({len(briefing.events)}):")
    if briefing.events:
        for event in briefing.events:
            time_str = event.start_time if event.all_day else f"{event.start_time} - {event.end_time}"
            location = f" at {event.location}" if event.location else ""
            lines.append(f"  {event.title} | {time_str}{location}")
    else:
        lines.append("  No events today.")

    w = briefing.weather
    lines.append("")
    lines.append("Weather in Porto:")
    lines.append(
        f"  {w.description}, {w.temperature_min_c}C - {w.temperature_max_c}C"
        f" (feels like up to {w.feels_like_max_c}C)"
    )
    lines.append(f"  Rain probability: {w.precipitation_probability}%, Wind: {w.wind_speed_max_kmh} km/h")
    if w.advice:
        lines.append(f"  Advice: {', '.join(w.advice)}")

    if briefing.holidays:
        lines.append("")
        lines.append("Holidays today:")
        for h in briefing.holidays:
            lines.append(f"  {h.local_name} ({h.country})")

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

    return "\n".join(lines)


class BriefingFormatterService:
    def __init__(self, llm_provider: LlmProvider, session: AsyncSession) -> None:
        self._llm_provider = llm_provider
        self._session = session

    async def format(self, briefing: MorningBriefing) -> FormattedBriefing:
        context = _build_context(briefing)
        messages = [{"role": "user", "content": context}]

        t0 = time_module.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=MORNING_BRIEFING_SYSTEM_PROMPT)
        latency_ms = int((time_module.monotonic() - t0) * 1000)

        text = llm_response.text.strip()

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
        await self._session.commit()

        return FormattedBriefing(date=briefing.date, text=text)
