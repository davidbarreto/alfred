from __future__ import annotations

import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.normalization import normalize_cf_difficulty, normalize_language, normalize_verdict
from app.features.cs.platforms.repository import PlatformRepository
from app.features.cs.platforms.schemas import PlatformUpdate
from app.features.cs.problems.schemas import ProblemCreate
from app.features.cs.problems.service import ProblemService
from app.features.cs.study_plans.service import StudyPlanService
from app.features.cs.submissions.schemas import SubmissionCreate
from app.features.cs.submissions.service import SubmissionService
from app.integrations.codeforces.client import CodeforcesClient

logger = logging.getLogger(__name__)

_PLATFORM_CODE = "codeforces"


class CodeforcesSyncService:

    def __init__(self, session: AsyncSession, client: CodeforcesClient | None = None) -> None:
        self._session = session
        self._client = client or CodeforcesClient()
        self._platforms = PlatformRepository(session)
        self._problems = ProblemService(session)
        self._submissions = SubmissionService(session)
        self._plans = StudyPlanService(session)

    async def sync(self) -> int:
        platform = await self._platforms.get_platform_by_code(_PLATFORM_CODE)
        if platform is None or not platform.sync_enabled or not platform.handle:
            logger.warning("Codeforces sync skipped: platform not configured")
            return 0

        try:
            info = await self._client.get_user_info(platform.handle)
            raw_submissions = await self._client.get_submissions_since(
                platform.handle, platform.last_submission_external_id
            )
        except Exception:
            logger.error("Codeforces sync failed: handle=%s", platform.handle, exc_info=True)
            raise

        count = 0
        max_external_id = platform.last_submission_external_id
        for raw in reversed(raw_submissions):
            if "verdict" not in raw:
                logger.debug("Codeforces sync: skipping submission id=%s, no verdict yet", raw.get("id"))
                continue

            problem_data = raw["problem"]
            external_problem_id = f"{problem_data['contestId']}{problem_data['index']}"
            rating = problem_data.get("rating")
            problem = await self._problems.upsert_problem(
                ProblemCreate(
                    platform_id=platform.id,
                    external_id=external_problem_id,
                    name=problem_data["name"],
                    url=f"https://codeforces.com/problemset/problem/{problem_data['contestId']}/{problem_data['index']}",
                    difficulty_raw=str(rating) if rating is not None else None,
                    difficulty=normalize_cf_difficulty(rating),
                    tags_raw=problem_data.get("tags", []),
                    tags=problem_data.get("tags", []),
                )
            )

            verdict_raw = raw["verdict"]
            submission = await self._submissions.upsert_submission(
                SubmissionCreate(
                    platform_id=platform.id,
                    problem_id=problem.id,
                    external_id=str(raw["id"]),
                    verdict=normalize_verdict(verdict_raw),
                    verdict_raw=verdict_raw,
                    language=normalize_language(raw.get("programmingLanguage")),
                    language_raw=raw.get("programmingLanguage"),
                    source_method="api_sync",
                    submitted_at=datetime.datetime.fromtimestamp(
                        raw["creationTimeSeconds"], tz=datetime.timezone.utc
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
                rating=info.get("rating"),
                max_rating=info.get("maxRating"),
                rank=info.get("rank"),
            ),
        )
        logger.info(
            "Codeforces sync completed: handle=%s new_submissions=%d", platform.handle, count
        )
        return count
