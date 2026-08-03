import datetime
import logging
import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.normalization import ALL_KNOWN_TAGS
from app.features.cs.stats.repository import StatsRepository
from app.features.cs.stats.schemas import (
    CandidateProblem,
    DailyActivity,
    DifficultyBreakdown,
    LanguageBreakdown,
    StatsSummary,
    TagBreakdown,
)

logger = logging.getLogger(__name__)

_DAILY_ACTIVITY_DAYS = 90
_MIN_ATTEMPTS_FOR_WEAK_TAG = 3
_WEAKEST_TAGS_LIMIT = 5
_WILSON_Z = 1.96  # 95% confidence
# Backstop so a tightly-clustered set of strong tags can't manufacture a fake
# "weakest" outlier just for being someone's relative minimum.
_MAX_SOLVE_RATE_FOR_WEAK_TAG = 0.85


def _wilson_lower_bound(solved: int, attempted: int, z: float = _WILSON_Z) -> float:
    """Lower bound of the Wilson score interval for a solve rate.

    A binomial proportion confidence interval: instead of trusting the raw
    solved/attempted ratio, this asks "what's the worst this rate is plausibly
    likely to be, given how much evidence backs it, at 95% confidence?". A 3/3
    tag (100% raw) has wide uncertainty and gets pulled down toward ~0.44; a
    30/30 tag (also 100%) has narrow uncertainty and stays close to 1.0. This
    is what lets low-attempt tags stop being ranked as confidently "strong"
    just because they haven't been tested enough to be wrong yet.

    Same formula Reddit used for comment ranking ("best" sort) and that's
    commonly recommended over raw ratios or normal-approximation intervals for
    small-n proportions:
    - https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval
    - https://www.evanmiller.org/how-not-to-sort-by-average-rating.html
    """
    if attempted == 0:
        return 0.0
    phat = solved / attempted
    margin = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * attempted)) / attempted)
    center = phat + z**2 / (2 * attempted)
    return (center - margin) / (1 + z**2 / attempted)


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
        total_attempted = await self._repo.get_total_attempted()

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
        by_day = [
            DailyActivity(date=day, attempts=attempts, solved=solved)
            for day, attempts, solved in await self._repo.get_daily_activity(_DAILY_ACTIVITY_DAYS)
        ]
        # Rank by the Wilson lower bound (confidence-adjusted solve rate), not raw
        # solve_rate, so a low-attempt tag with a lucky 100% isn't ranked "strong".
        # A tag only qualifies as "weakest" if it's both below your own overall
        # average and below an absolute competence floor — otherwise a tightly
        # clustered set of 90%+ tags would fill the list just for being the
        # relative minimum among otherwise-strong tags.
        eligible_tags = [t for t in by_tag if t.attempted >= _MIN_ATTEMPTS_FOR_WEAK_TAG]
        eligible_attempted = sum(t.attempted for t in eligible_tags)
        overall_solve_rate = (
            sum(t.solved for t in eligible_tags) / eligible_attempted if eligible_attempted else 0.0
        )
        weakest_tags = sorted(
            (
                t
                for t in eligible_tags
                if t.solve_rate < _MAX_SOLVE_RATE_FOR_WEAK_TAG
                and _wilson_lower_bound(t.solved, t.attempted) < overall_solve_rate
            ),
            key=lambda t: (
                _wilson_lower_bound(t.solved, t.attempted),
                -(t.avg_attempts_per_solve or 0),
            ),
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
            total_attempted=total_attempted,
            by_difficulty=by_difficulty,
            by_tag=by_tag,
            by_language=by_language,
            by_day=by_day,
            weakest_tags=weakest_tags,
            untried_tags=untried_tags,
        )
