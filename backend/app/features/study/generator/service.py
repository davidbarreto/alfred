import json
import logging
import time as time_module

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.stats.schemas import CandidateProblem, TagBreakdown
from app.features.cs.stats.service import StatsService
from app.features.study.generator.prompts import CS_STATS_PLAN_SYSTEM_PROMPT
from app.features.study.plans.schemas import StudyPlanCreate, StudyPlanItemCreate, StudyPlanRead
from app.features.study.plans.service import StudyPlanService
from app.features.study.tracks.service import SOFTWARE_ENGINEERING_TRACK, StudyTrackService
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_PLAN_CANDIDATE_LIMIT = 15
_MAX_TAGS = 3
_PRIORITIES = {"low", "medium", "high"}


class StudyTrackNotFoundError(Exception):
    """Raised when the track a generator targets hasn't been seeded."""


class PlanGenerationError(Exception):
    """Raised when the LLM response can't be turned into a usable plan."""


def _build_cs_stats_context(
    total_solved: int,
    total_attempted: int,
    weakest_tags: list[TagBreakdown],
    candidates: list[CandidateProblem],
    low_confidence: bool,
    existing_tags: list[str],
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

    lines.append("")
    lines.append(f"Existing study tags: {', '.join(existing_tags) if existing_tags else 'none yet'}")

    return "\n".join(lines)


def _parse_items(raw_items: list, candidate_by_external_id: dict[str, CandidateProblem]) -> list[StudyPlanItemCreate]:
    """Problem suggestions must come from the candidate list; they keep the candidate's own URL."""
    items = []
    for raw_item in raw_items:
        description = (raw_item.get("description") or "").strip()
        if not description:
            continue
        url = raw_item.get("url")
        external_id = raw_item.get("candidate_external_id")
        if external_id is not None:
            candidate = candidate_by_external_id.get(external_id)
            if candidate is None:
                logger.warning("Study plan generation: LLM referenced unknown candidate_external_id=%r", external_id)
                continue
            url = candidate.url
        # source_id stays unset until CS tags are exposed by id to the generator (phase 2 evidence work).
        items.append(StudyPlanItemCreate(description=description, url=url, position=len(items), source_type="cs_tag"))
    return items


def _parse_tags(raw_tags: list) -> list[str]:
    tags: list[str] = []
    for raw_tag in raw_tags:
        tag = str(raw_tag).strip().lower()
        if tag and tag not in tags:
            tags.append(tag[:255])
    return tags[:_MAX_TAGS]


class StudyPlanGeneratorService:

    def __init__(self, llm_provider: LlmProvider, session: AsyncSession) -> None:
        self._llm_provider = llm_provider
        self._session = session
        self._stats = StatsService(session)
        self._tracks = StudyTrackService(session)
        self._plans = StudyPlanService(session)

    async def generate_from_cs_stats(self) -> StudyPlanRead:
        track = await self._tracks.get_track_by_name(SOFTWARE_ENGINEERING_TRACK)
        if track is None:
            logger.error("Study plan generation: track %r not seeded", SOFTWARE_ENGINEERING_TRACK)
            raise StudyTrackNotFoundError(SOFTWARE_ENGINEERING_TRACK)

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

        context = _build_cs_stats_context(
            summary.total_solved,
            summary.total_attempted,
            weakest_tags,
            candidates,
            low_confidence,
            await self._plans.get_tag_names(),
        )
        messages = [{"role": "user", "content": context}]

        t0 = time_module.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=CS_STATS_PLAN_SYSTEM_PROMPT)
        latency_ms = int((time_module.monotonic() - t0) * 1000)

        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="study_plan_cs_stats",
            prompt=messages,
            response=raw,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            finish_reason=llm_response.finish_reason,
            latency_ms=latency_ms,
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Study plan generation: invalid JSON: %r", raw[:200])
            raise PlanGenerationError("LLM returned invalid JSON for study plan") from exc

        title = (parsed.get("title") or "").strip()
        goal = (parsed.get("goal") or "").strip()
        items = _parse_items(parsed.get("items") or [], {c.external_id: c for c in candidates})
        if not title or not goal or not items:
            logger.warning(
                "Study plan generation: incomplete plan title=%r goal_set=%s items=%d", title, bool(goal), len(items)
            )
            raise PlanGenerationError("LLM returned an incomplete study plan")

        priority = parsed.get("priority")
        plan = await self._plans.create_plan(
            StudyPlanCreate(
                track_id=track.id,
                title=title[:255],
                goal=goal,
                priority=priority if priority in _PRIORITIES else "medium",
                tags=_parse_tags(parsed.get("tags") or []),
                items=items,
            )
        )
        logger.info("Study plan generated from CS stats: id=%d status=%s items=%d", plan.id, plan.status, len(items))
        return plan
