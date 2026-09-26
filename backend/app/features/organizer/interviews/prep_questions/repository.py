from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion, InterviewPrepQuestionStory
from app.features.organizer.interviews.stories.tables import InterviewStory


class InterviewPrepQuestionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_question(self, question_id: int) -> InterviewPrepQuestion | None:
        stmt = (
            select(InterviewPrepQuestion)
            .where(InterviewPrepQuestion.id == question_id)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_question_with_links(self, question_id: int) -> InterviewPrepQuestion | None:
        stmt = (
            select(InterviewPrepQuestion)
            .where(InterviewPrepQuestion.id == question_id)
            .options(
                selectinload(InterviewPrepQuestion.story_links)
                .selectinload(InterviewPrepQuestionStory.story)
                .selectinload(InterviewStory.tags)
            )
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_questions(self, limit: int = 100, offset: int = 0) -> list[InterviewPrepQuestion]:
        stmt = (
            select(InterviewPrepQuestion)
            .order_by(InterviewPrepQuestion.created_at.desc(), InterviewPrepQuestion.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def create_question(self, text: str) -> InterviewPrepQuestion:
        question = InterviewPrepQuestion(text=text)
        self._session.add(question)
        await self._session.commit()
        refreshed = await self.get_question(question.id)
        assert refreshed is not None
        return refreshed

    async def update_question(self, question_id: int, text: str | None) -> InterviewPrepQuestion | None:
        question = await self.get_question(question_id)
        if question is None:
            return None
        if text is not None:
            question.text = text
        await self._session.commit()
        return await self.get_question(question_id)

    async def delete_question(self, question_id: int) -> bool:
        question = await self._session.get(InterviewPrepQuestion, question_id)
        if question is None:
            return False
        await self._session.delete(question)
        await self._session.commit()
        return True

    async def story_exists(self, story_id: int) -> bool:
        return await self._session.get(InterviewStory, story_id) is not None

    async def link_story(self, question_id: int, story_id: int, fit_score: int) -> InterviewPrepQuestionStory:
        stmt = select(InterviewPrepQuestionStory).where(
            InterviewPrepQuestionStory.question_id == question_id,
            InterviewPrepQuestionStory.story_id == story_id,
        )
        link = await self._session.scalar(stmt)
        if link is None:
            link = InterviewPrepQuestionStory(question_id=question_id, story_id=story_id, fit_score=fit_score)
            self._session.add(link)
        else:
            link.fit_score = fit_score
        await self._session.commit()
        return link

    async def unlink_story(self, question_id: int, story_id: int) -> bool:
        stmt = delete(InterviewPrepQuestionStory).where(
            InterviewPrepQuestionStory.question_id == question_id,
            InterviewPrepQuestionStory.story_id == story_id,
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
