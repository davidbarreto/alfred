from __future__ import annotations

import asyncio
import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.normalization import normalize_language, normalize_leetcode_difficulty, normalize_verdict
from app.features.cs.platforms.repository import PlatformRepository
from app.features.cs.platforms.schemas import PlatformUpdate
from app.features.cs.problems.schemas import ProblemCreate, ProblemUpdate
from app.features.cs.problems.service import ProblemService
from app.features.cs.study_plans.service import StudyPlanService
from app.features.cs.submissions.schemas import SubmissionCreate
from app.features.cs.submissions.service import SubmissionService
from app.integrations.leetcode.client import LeetCodeClient

logger = logging.getLogger(__name__)

_PLATFORM_CODE = "leetcode"
_METRICS_REQUEST_DELAY_SECONDS = 1.0


class LeetCodeSyncService:

    def __init__(self, session: AsyncSession, client: LeetCodeClient) -> None:
        self._session = session
        self._client = client
        self._platforms = PlatformRepository(session)
        self._problems = ProblemService(session)
        self._submissions = SubmissionService(session)
        self._plans = StudyPlanService(session)

    async def sync(self) -> int:
        platform = await self._platforms.get_platform_by_code(_PLATFORM_CODE)
        if platform is None or not platform.sync_enabled:
            logger.warning("LeetCode sync skipped: platform not configured")
            return 0

        raw_submissions = await self._client.get_submissions_since(
            platform.last_submission_external_id
        )

        count = 0
        max_external_id = platform.last_submission_external_id
        question_cache: dict[str, dict] = {}
        for raw in reversed(raw_submissions):
            title_slug = raw["titleSlug"]
            if title_slug not in question_cache:
                question_cache[title_slug] = await self._client.get_question_data(title_slug)
            question = question_cache[title_slug]
            tag_names = [t["name"] for t in question.get("topicTags", [])]

            problem = await self._problems.upsert_problem(
                ProblemCreate(
                    platform_id=platform.id,
                    external_id=title_slug,
                    name=question["title"],
                    url=f"https://leetcode.com/problems/{title_slug}/",
                    difficulty_raw=question.get("difficulty"),
                    difficulty=normalize_leetcode_difficulty(question.get("difficulty")),
                    tags_raw=tag_names,
                    tags=tag_names,
                )
            )

            verdict_raw = raw["statusDisplay"]
            submission = await self._submissions.upsert_submission(
                SubmissionCreate(
                    platform_id=platform.id,
                    problem_id=problem.id,
                    external_id=str(raw["id"]),
                    verdict=normalize_verdict(verdict_raw),
                    verdict_raw=verdict_raw,
                    language=normalize_language(raw.get("lang")),
                    language_raw=raw.get("lang"),
                    source_method="api_sync",
                    submitted_at=datetime.datetime.fromtimestamp(
                        int(raw["timestamp"]), tz=datetime.timezone.utc
                    ),
                )
            )
            if submission.verdict == "accepted":
                await self._plans.auto_complete_items_for_problem(problem.id)

            count += 1
            max_external_id = str(raw["id"])

        await self._platforms.update_platform(
            platform.id,
            PlatformUpdate(
                last_synced_at=datetime.datetime.now(datetime.timezone.utc),
                last_submission_external_id=max_external_id,
            ),
        )
        logger.info("LeetCode sync completed: new_submissions=%d", count)
        return count

    async def refresh_metrics(self) -> int:
        """Refetch acceptance rate/likes/dislikes for every previously-synced LeetCode problem."""
        platform = await self._platforms.get_platform_by_code(_PLATFORM_CODE)
        if platform is None:
            logger.warning("LeetCode metrics refresh skipped: platform not configured")
            return 0

        problems = await self._problems.get_problems_by_platform(platform.id)
        updated = 0
        now = datetime.datetime.now(datetime.timezone.utc)
        for problem in problems:
            question = await self._client.get_question_data(problem.external_id)
            await self._problems.update_problem(
                problem.id,
                ProblemUpdate(
                    acceptance_rate=question.get("acRate"),
                    likes=question.get("likes"),
                    dislikes=question.get("dislikes"),
                    metrics_updated_at=now,
                ),
            )
            updated += 1
            await asyncio.sleep(_METRICS_REQUEST_DELAY_SECONDS)

        await self._platforms.update_platform(platform.id, PlatformUpdate(metrics_refreshed_at=now))
        logger.info("LeetCode metrics refresh completed: updated=%d", updated)
        return updated
