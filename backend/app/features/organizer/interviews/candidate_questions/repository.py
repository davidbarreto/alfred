from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.candidate_questions.tables import InterviewCandidateQuestion


class InterviewCandidateQuestionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_question(self, question_id: int) -> InterviewCandidateQuestion | None:
        stmt = (
            select(InterviewCandidateQuestion)
            .where(InterviewCandidateQuestion.id == question_id)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_questions(
        self, category: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[InterviewCandidateQuestion]:
        stmt = select(InterviewCandidateQuestion)
        if category is not None:
            stmt = stmt.where(InterviewCandidateQuestion.category == category)
        stmt = (
            stmt.order_by(
                InterviewCandidateQuestion.category,
                InterviewCandidateQuestion.created_at.desc(),
                InterviewCandidateQuestion.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def create_question(self, text: str, category: str) -> InterviewCandidateQuestion:
        question = InterviewCandidateQuestion(text=text, category=category)
        self._session.add(question)
        await self._session.commit()
        refreshed = await self.get_question(question.id)
        assert refreshed is not None
        return refreshed

    async def update_question(self, question_id: int, fields: dict[str, Any]) -> InterviewCandidateQuestion | None:
        question = await self.get_question(question_id)
        if question is None:
            return None
        for name, value in fields.items():
            setattr(question, name, value)
        await self._session.commit()
        return await self.get_question(question_id)

    async def delete_question(self, question_id: int) -> bool:
        question = await self._session.get(InterviewCandidateQuestion, question_id)
        if question is None:
            return False
        await self._session.delete(question)
        await self._session.commit()
        return True

    async def get_all_categories(self) -> list[str]:
        stmt = select(InterviewCandidateQuestion.category).distinct().order_by(InterviewCandidateQuestion.category)
        return list((await self._session.scalars(stmt)).all())
