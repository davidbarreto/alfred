import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.candidate_questions.repository import InterviewCandidateQuestionRepository
from app.features.organizer.interviews.candidate_questions.schemas import (
    InterviewCandidateQuestionCreate,
    InterviewCandidateQuestionRead,
    InterviewCandidateQuestionUpdate,
)

logger = logging.getLogger(__name__)


class InterviewCandidateQuestionService:
    def __init__(self, session: AsyncSession):
        self._repo = InterviewCandidateQuestionRepository(session)

    async def get_question(self, question_id: int) -> InterviewCandidateQuestionRead | None:
        question = await self._repo.get_question(question_id)
        return InterviewCandidateQuestionRead.model_validate(question) if question else None

    async def get_questions(
        self, category: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[InterviewCandidateQuestionRead]:
        questions = await self._repo.get_questions(category=category, limit=limit, offset=offset)
        return [InterviewCandidateQuestionRead.model_validate(q) for q in questions]

    async def create_question(self, data: InterviewCandidateQuestionCreate) -> InterviewCandidateQuestionRead:
        question = await self._repo.create_question(text=data.text, category=data.category)
        logger.info("Interview candidate question created: id=%d category=%r", question.id, question.category)
        return InterviewCandidateQuestionRead.model_validate(question)

    async def update_question(
        self, question_id: int, data: InterviewCandidateQuestionUpdate
    ) -> InterviewCandidateQuestionRead | None:
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        question = await self._repo.update_question(question_id, fields=changes)
        if question is None:
            logger.debug("Interview candidate question update: id=%d not found", question_id)
            return None
        logger.info("Interview candidate question updated: id=%d fields=%s", question_id, list(changes))
        return InterviewCandidateQuestionRead.model_validate(question)

    async def delete_question(self, question_id: int) -> bool:
        deleted = await self._repo.delete_question(question_id)
        if deleted:
            logger.info("Interview candidate question deleted: id=%d", question_id)
        return deleted

    async def get_all_categories(self) -> list[str]:
        return await self._repo.get_all_categories()
