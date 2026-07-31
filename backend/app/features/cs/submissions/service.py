import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.submissions.repository import SubmissionRepository
from app.features.cs.submissions.schemas import SubmissionCreate, SubmissionFilters, SubmissionRead

logger = logging.getLogger(__name__)


class SubmissionService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SubmissionRepository(session)

    async def get_submission(self, submission_id: int) -> SubmissionRead | None:
        orm = await self._repo.get_submission(submission_id)
        return SubmissionRead.model_validate(orm) if orm else None

    async def get_submissions(self, filters: SubmissionFilters) -> list[SubmissionRead]:
        submissions = await self._repo.get_submissions(filters)
        return [SubmissionRead.model_validate(s) for s in submissions]

    async def create_submission(self, data: SubmissionCreate) -> SubmissionRead:
        orm = await self._repo.create_submission(data)
        logger.info(
            "Submission created: id=%d platform_id=%d problem_id=%d verdict=%s",
            orm.id, orm.platform_id, orm.problem_id, orm.verdict,
        )
        return SubmissionRead.model_validate(orm)

    async def upsert_submission(self, data: SubmissionCreate) -> SubmissionRead:
        orm = await self._repo.upsert_submission(data)
        logger.debug(
            "Submission upserted: platform_id=%d external_id=%r", data.platform_id, data.external_id
        )
        return SubmissionRead.model_validate(orm)
