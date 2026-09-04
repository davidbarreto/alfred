from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.companies.repository import CompanyRepository
from app.features.organizer.interviews.insights.prompts import INSIGHTS_SYSTEM_PROMPT_TEMPLATE
from app.features.organizer.interviews.insights.repository import InterviewInsightRepository
from app.features.organizer.interviews.insights.schemas import (
    InsightsResult,
    InterviewInsightFilters,
    InterviewInsightRead,
)
from app.features.organizer.interviews.processes.repository import InterviewProcessRepository
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


class InterviewInsightService:
    def __init__(self, session: AsyncSession, llm_provider: LlmProvider) -> None:
        self._session = session
        self._llm_provider = llm_provider
        self._repo = InterviewInsightRepository(session)
        self._process_repo = InterviewProcessRepository(session)
        self._company_repo = CompanyRepository(session)

    async def _build_process_summary(self, now: datetime) -> tuple[str, list[int]]:
        processes = await self._process_repo.get_active_processes()
        entries = []
        for process in processes:
            company = await self._company_repo.get_company(process.company_id)
            company_name = company.name if company else "Unknown company"
            stage_lines = ", ".join(
                f"{s.stage_type} ({s.status}, {s.scheduled_at or 'unscheduled'})" for s in process.stages
            ) or "no stages recorded yet"

            upcoming = [s for s in process.stages if s.status == "scheduled" and s.scheduled_at is not None]
            next_stage = min(upcoming, key=lambda s: s.scheduled_at) if upcoming else None
            days_until: int | None = None
            if next_stage is not None:
                scheduled_at = next_stage.scheduled_at
                if scheduled_at.tzinfo is None:
                    scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
                days_until = (scheduled_at.date() - now.date()).days
                next_summary = f"NEXT: {next_stage.stage_type} in {days_until} day(s), on {scheduled_at.date()}"
            else:
                next_summary = "NEXT: nothing scheduled"

            entries.append({
                "id": process.id,
                "company": company_name,
                "role": process.role_title,
                "priority": process.priority or "unset",
                "study_plan_id": process.study_plan_id,
                "next_summary": next_summary,
                "stage_lines": stage_lines,
                "days_until": days_until,
            })

        entries.sort(key=lambda e: (e["days_until"] is None, e["days_until"]))

        lines = [
            f"- Process id {e['id']}: {e['company']} — {e['role']} (priority={e['priority']}, "
            f"study_plan_id={e['study_plan_id']}). {e['next_summary']}. Full stage history: {e['stage_lines']}"
            for e in entries
        ]
        return "\n".join(lines) or "No active interview processes.", [e["id"] for e in entries]

    async def generate_insights(self) -> InterviewInsightRead:
        now = datetime.now(timezone.utc)
        processes_summary, process_ids = await self._build_process_summary(now)
        schema_str = json.dumps(InsightsResult.model_json_schema(), indent=2)
        system_prompt = INSIGHTS_SYSTEM_PROMPT_TEMPLATE.format(
            schema=schema_str, processes=processes_summary, today=now.date()
        )
        messages = [{"role": "user", "content": "What should I focus on this week?"}]

        t0 = time.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=system_prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="interview_insights",
            prompt=[{"role": "system", "content": system_prompt}] + messages,
            response=llm_response.text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            finish_reason=llm_response.finish_reason,
            latency_ms=latency_ms,
        )

        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = InsightsResult.model_validate_json(raw)

        insight = await self._repo.create_insight(
            content=parsed.content,
            model=self._llm_provider.model,
            process_ids=process_ids,
            generated_at=now,
        )
        logger.info("Interview insight generated: id=%d process_count=%d", insight.id, len(process_ids))
        return InterviewInsightRead.model_validate(insight)

    async def get_insights_history(self, filters: InterviewInsightFilters) -> list[InterviewInsightRead]:
        insights = await self._repo.get_insights(filters)
        return [InterviewInsightRead.model_validate(i) for i in insights]
