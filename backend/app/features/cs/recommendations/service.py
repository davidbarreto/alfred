from __future__ import annotations

import datetime
import json
import logging
import time as time_module

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.recommendations.prompts import STUDY_PLAN_SYSTEM_PROMPT
from app.features.cs.recommendations.schemas import LiveRecommendation
from app.features.cs.stats.service import StatsService
from app.features.cs.study_plans.schemas import StudyPlanCreate, StudyPlanItemCreate, StudyPlanRead
from app.features.cs.study_plans.service import StudyPlanService
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_LIVE_CANDIDATE_LIMIT = 5
_PLAN_CANDIDATE_LIMIT = 15


def _build_plan_context(
    total_solved: int, total_attempted: int, weakest_tags: list, candidates: list, low_confidence: bool
) -> str:
    lines = [f"Overall: {total_solved} problems solved across {total_attempted} attempts."]
    if low_confidence:
        lines.append(
            "No single tag has enough attempts yet to confidently call it a weakness -- "
            "this reflects thin per-tag coverage, not a lack of overall practice. "
            "Least-practiced tags so far (name, solve rate, attempted):"
        )
    else:
        lines.append("Weakest tags (name, solve rate, attempted):")
    for t in weakest_tags:
        lines.append(f"  {t.tag} | solve_rate={t.solve_rate:.0%} | attempted={t.attempted}")

    lines.append("")
    lines.append("Candidate unsolved problems (external_id, name, difficulty, tags):")
    for c in candidates:
        tags = ", ".join(c.tags) if c.tags else "untagged"
        lines.append(f"  {c.external_id} | {c.name} | {c.difficulty or 'unknown'} | {tags}")

    return "\n".join(lines)


class RecommendationService:

    def __init__(self, llm_provider: LlmProvider, session: AsyncSession) -> None:
        self._llm_provider = llm_provider
        self._session = session
        self._stats = StatsService(session)
        self._plans = StudyPlanService(session)

    async def get_live_recommendation(self) -> LiveRecommendation | None:
        summary = await self._stats.get_summary()
        if summary.total_solved == 0:
            return None
        if not summary.weakest_tags:
            return await self._get_strong_performance_recommendation(summary)
        weakest = summary.weakest_tags[0]
        candidates = await self._stats.get_candidate_problems([weakest.tag], limit=_LIVE_CANDIDATE_LIMIT)
        return LiveRecommendation(
            tag=weakest.tag,
            solve_rate=weakest.solve_rate,
            reason=f"Your solve rate on {weakest.tag} is {weakest.solve_rate:.0%} over {weakest.attempted} attempts, your weakest tracked tag.",
            candidates=candidates,
        )

    async def _get_strong_performance_recommendation(self, summary) -> LiveRecommendation:
        """No tag qualifies as "weakest" -- solve rates are uniformly high. Nudge toward
        breadth (an untried tag) rather than reporting this as missing history."""
        if summary.untried_tags:
            tag = summary.untried_tags[0]
            candidates = await self._stats.get_candidate_problems([tag], limit=_LIVE_CANDIDATE_LIMIT)
            return LiveRecommendation(
                tag=tag,
                solve_rate=None,
                reason=f"You're solid across every tracked tag -- try something new: {tag}.",
                candidates=candidates,
            )
        return LiveRecommendation(
            tag=None,
            solve_rate=None,
            reason="You're solid across every tracked tag and have tried them all. Keep pushing difficulty.",
            candidates=[],
        )

    async def generate_plan(self, cadence: str) -> StudyPlanRead:
        summary = await self._stats.get_summary()
        low_confidence = not summary.weakest_tags
        if low_confidence:
            # No tag cleared the weakness bar (not enough attempts, or solve rates are
            # uniformly healthy). Fall back to the least-practiced tags -- ranked by
            # fewest attempts, then lowest solve rate -- so the plan targets genuine
            # gaps in evidence instead of whatever tags sort first alphabetically.
            weakest_tags = sorted(summary.by_tag, key=lambda t: (t.attempted, t.solve_rate))[:3]
        else:
            weakest_tags = summary.weakest_tags
        tag_names = [t.tag for t in weakest_tags] or None
        candidates = await self._stats.get_candidate_problems(tag_names, limit=_PLAN_CANDIDATE_LIMIT)
        candidate_by_external_id = {c.external_id: c.id for c in candidates}

        context = _build_plan_context(
            summary.total_solved, summary.total_attempted, weakest_tags, candidates, low_confidence
        )
        messages = [{"role": "user", "content": context}]

        t0 = time_module.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=STUDY_PLAN_SYSTEM_PROMPT)
        latency_ms = int((time_module.monotonic() - t0) * 1000)

        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="cs_study_plan",
            prompt=messages,
            response=raw,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            finish_reason=llm_response.finish_reason,
            latency_ms=latency_ms,
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Study plan generation: invalid JSON for cadence=%s: %r", cadence, raw[:200])
            raise ValueError("LLM returned invalid JSON for study plan")

        items = []
        for position, raw_item in enumerate(parsed.get("items", [])):
            item_type = raw_item.get("item_type")
            problem_id = None
            if item_type == "problem":
                external_id = raw_item.get("candidate_external_id")
                problem_id = candidate_by_external_id.get(external_id)
                if problem_id is None:
                    logger.warning(
                        "Study plan generation: LLM referenced unknown candidate_external_id=%r", external_id
                    )
                    continue
            items.append(
                StudyPlanItemCreate(
                    item_type=item_type,
                    description=raw_item.get("description", ""),
                    problem_id=problem_id,
                    url=raw_item.get("url"),
                    position=position,
                )
            )

        plan = await self._plans.create_plan(
            StudyPlanCreate(
                cadence=cadence,
                period_start=datetime.datetime.now(datetime.timezone.utc).date(),
                rationale=parsed.get("rationale"),
                items=items,
            )
        )
        logger.info("Study plan generated: cadence=%s items=%d", cadence, len(items))
        return plan
