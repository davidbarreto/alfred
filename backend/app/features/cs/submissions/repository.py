from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.submissions.schemas import SubmissionCreate, SubmissionFilters
from app.features.cs.submissions.tables import Submission


class SubmissionRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_submission(self, submission_id: int) -> Submission | None:
        result = await self._session.execute(select(Submission).where(Submission.id == submission_id))
        return result.scalars().first()

    async def get_submission_by_external_id(self, platform_id: int, external_id: str) -> Submission | None:
        result = await self._session.execute(
            select(Submission).where(
                Submission.platform_id == platform_id, Submission.external_id == external_id
            )
        )
        return result.scalars().first()

    async def get_submissions(self, filters: SubmissionFilters) -> list[Submission]:
        query = select(Submission)
        if filters.platform_id is not None:
            query = query.where(Submission.platform_id == filters.platform_id)
        if filters.problem_id is not None:
            query = query.where(Submission.problem_id == filters.problem_id)
        if filters.verdict is not None:
            query = query.where(Submission.verdict == filters.verdict)
        if filters.language is not None:
            query = query.where(Submission.language == filters.language)
        query = query.order_by(Submission.submitted_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create_submission(self, data: SubmissionCreate) -> Submission:
        submission = Submission(**data.model_dump())
        self._session.add(submission)
        await self._session.commit()
        await self._session.refresh(submission)
        return submission

    async def upsert_submission(self, data: SubmissionCreate) -> Submission:
        existing = await self.get_submission_by_external_id(data.platform_id, data.external_id)
        if existing is not None:
            return existing
        return await self.create_submission(data)
