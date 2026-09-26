from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.candidate_questions.tables import InterviewCandidateQuestion


class InterviewCandidateQuestionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_question(self, question_id: int) -> InterviewCandidateQuestion | None:
        stmt = select(InterviewCandidateQuestion).where(InterviewCandidateQuestion.id == question_id)
        return await self._session.scalar(stmt)

    async def get_questions(self, limit: int = 100, offset: int = 0) -> list[InterviewCandidateQuestion]:
        stmt = (
            select(InterviewCandidateQuestion)
            .order_by(InterviewCandidateQuestion.category, InterviewCandidateQuestion.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return await self._session.scalars(stmt)

    async def get_questions_by_category(self, category: str, limit: int = 100, offset: int = 0) -> list[InterviewCandidateQuestion]:
        stmt = (
            select(InterviewCandidateQuestion)
            .where(InterviewCandidateQuestion.category == category)
            .order_by(InterviewCandidateQuestion.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return await self._session.scalars(stmt)

    async def create_question(self, text: str, category: str) -> InterviewCandidateQuestion:
        question = InterviewCandidateQuestion(text=text, category=category)
        self._session.add(question)
        await self._session.flush()
        return question

    async def update_question(
        self, question_id: int, text: str | None = None, category: str | None = None
    ) -> InterviewCandidateQuestion | None:
        question = await self.get_question(question_id)
        if not question:
            return None

        if text is not None:
            question.text = text
        if category is not None:
            question.category = category

        await self._session.flush()
        return question

    async def delete_question(self, question_id: int) -> bool:
        question = await self.get_question(question_id)
        if not question:
            return False
        await self._session.delete(question)
        await self._session.flush()
        return True

    async def get_all_categories(self) -> list[str]:
        stmt = select(InterviewCandidateQuestion.category).distinct().order_by(InterviewCandidateQuestion.category)
        result = await self._session.scalars(stmt)
        return list(result)
