import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.candidate_questions.repository import InterviewCandidateQuestionRepository
from app.features.organizer.interviews.candidate_questions.schemas import InterviewCandidateQuestionCreate, InterviewCandidateQuestionUpdate
from app.features.organizer.interviews.candidate_questions.tables import InterviewCandidateQuestion

logger = logging.getLogger(__name__)


class InterviewCandidateQuestionService:
    def __init__(self, session: AsyncSession):
        self._repo = InterviewCandidateQuestionRepository(session)

    async def get_question(self, question_id: int) -> InterviewCandidateQuestion | None:
        return await self._repo.get_question(question_id)

    async def get_questions(self, limit: int = 100, offset: int = 0) -> list[InterviewCandidateQuestion]:
        return await self._repo.get_questions(limit=limit, offset=offset)

    async def get_questions_by_category(self, category: str, limit: int = 100, offset: int = 0) -> list[InterviewCandidateQuestion]:
        return await self._repo.get_questions_by_category(category=category, limit=limit, offset=offset)

    async def create_question(self, data: InterviewCandidateQuestionCreate) -> InterviewCandidateQuestion:
        question = await self._repo.create_question(text=data.text, category=data.category)
        logger.info("Interview candidate question created: id=%d category=%r", question.id, question.category)
        return question

    async def update_question(self, question_id: int, data: InterviewCandidateQuestionUpdate) -> InterviewCandidateQuestion | None:
        question = await self._repo.update_question(question_id=question_id, text=data.text, category=data.category)
        if question:
            logger.info("Interview candidate question updated: id=%d", question_id)
        return question

    async def delete_question(self, question_id: int) -> bool:
        result = await self._repo.delete_question(question_id)
        if result:
            logger.info("Interview candidate question deleted: id=%d", question_id)
        return result

    async def get_all_categories(self) -> list[str]:
        return await self._repo.get_all_categories()
