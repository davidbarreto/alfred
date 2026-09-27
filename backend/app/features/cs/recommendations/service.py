import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.recommendations.schemas import LiveRecommendation
from app.features.cs.stats.service import StatsService

logger = logging.getLogger(__name__)

_LIVE_CANDIDATE_LIMIT = 5


class RecommendationService:

    def __init__(self, session: AsyncSession) -> None:
        self._stats = StatsService(session)

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
