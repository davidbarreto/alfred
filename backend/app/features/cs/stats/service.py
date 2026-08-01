import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.normalization import ALL_KNOWN_TAGS
from app.features.cs.stats.repository import StatsRepository
from app.features.cs.stats.schemas import (
    CandidateProblem,
    DifficultyBreakdown,
    LanguageBreakdown,
    StatsSummary,
    TagBreakdown,
)

logger = logging.getLogger(__name__)

_MIN_ATTEMPTS_FOR_WEAK_TAG = 3
_WEAKEST_TAGS_LIMIT = 5


def compute_streaks(solved_dates: list[datetime.date]) -> tuple[int, int]:
    """Pure function: consecutive-day streaks over sorted, deduped solve dates."""
    if not solved_dates:
        return 0, 0

    longest = current = 1
    for previous, day in zip(solved_dates, solved_dates[1:]):
        if (day - previous).days == 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)

    today = datetime.datetime.now(datetime.timezone.utc).date()
    gap_to_today = (today - solved_dates[-1]).days
    current_streak = current if gap_to_today <= 1 else 0
    return current_streak, longest


class StatsService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = StatsRepository(session)

    async def get_candidate_problems(
        self, tag_names: list[str] | None = None, limit: int = 10
    ) -> list[CandidateProblem]:
        problems = await self._repo.get_unsolved_candidate_problems(tag_names, limit)
        return [
            CandidateProblem(
                id=p.id,
                platform_id=p.platform_id,
                external_id=p.external_id,
                name=p.name,
                url=p.url,
                difficulty=p.difficulty,
                tags=[t.name for t in p.tags],
            )
            for p in problems
        ]

    async def get_summary(self) -> StatsSummary:
        solved_dates = await self._repo.get_solved_dates()
        current_streak, longest_streak = compute_streaks(solved_dates)
        total_solved = await self._repo.get_total_solved()

        by_difficulty = [
            DifficultyBreakdown(difficulty=difficulty, attempted=attempted, solved=solved)
            for difficulty, attempted, solved in await self._repo.get_difficulty_breakdown()
        ]
        by_tag = [
            TagBreakdown(
                tag=tag,
                attempted=attempted,
                solved=solved,
                solve_rate=solved / attempted,
                submissions=submissions,
                avg_attempts_per_solve=submissions / solved if solved else None,
            )
            for tag, attempted, solved, submissions in await self._repo.get_tag_breakdown()
        ]
        by_language = [
            LanguageBreakdown(language=language, solved=solved)
            for language, solved in await self._repo.get_language_breakdown()
        ]
        # Primary: lowest solve rate first. Tiebreak: more submissions per solve (more
        # struggle to get there) ranks weaker among tags with the same solve rate.
        weakest_tags = sorted(
            (t for t in by_tag if t.attempted >= _MIN_ATTEMPTS_FOR_WEAK_TAG),
            key=lambda t: (t.solve_rate, -(t.avg_attempts_per_solve or 0)),
        )[:_WEAKEST_TAGS_LIMIT]
        untried_tags = sorted(set(ALL_KNOWN_TAGS) - {t.tag for t in by_tag})

        logger.debug(
            "Stats summary computed: total_solved=%d current_streak=%d longest_streak=%d",
            total_solved, current_streak, longest_streak,
        )
        return StatsSummary(
            current_streak=current_streak,
            longest_streak=longest_streak,
            total_solved=total_solved,
            by_difficulty=by_difficulty,
            by_tag=by_tag,
            by_language=by_language,
            weakest_tags=weakest_tags,
            untried_tags=untried_tags,
        )
