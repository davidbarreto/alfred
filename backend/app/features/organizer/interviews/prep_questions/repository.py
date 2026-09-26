from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion, InterviewPrepQuestionStory
from app.features.organizer.interviews.stories.tables import InterviewStory, InterviewStoryTag


class InterviewPrepQuestionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_question(self, question_id: int) -> InterviewPrepQuestion | None:
        stmt = select(InterviewPrepQuestion).where(InterviewPrepQuestion.id == question_id)
        return await self._session.scalar(stmt)

    async def get_question_with_stories(self, question_id: int) -> InterviewPrepQuestion | None:
        stmt = (
            select(InterviewPrepQuestion)
            .where(InterviewPrepQuestion.id == question_id)
            .options(
                selectinload(InterviewPrepQuestion.story_links).selectinload(InterviewPrepQuestionStory.question),
                selectinload(InterviewPrepQuestion.stories).selectinload(InterviewStory.tags),
            )
        )
        return await self._session.scalar(stmt)

    async def get_questions(self, limit: int = 100, offset: int = 0) -> list[InterviewPrepQuestion]:
        stmt = (
            select(InterviewPrepQuestion)
            .order_by(InterviewPrepQuestion.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return await self._session.scalars(stmt)

    async def create_question(self, text: str) -> InterviewPrepQuestion:
        question = InterviewPrepQuestion(text=text)
        self._session.add(question)
        await self._session.flush()
        return question

    async def update_question(self, question_id: int, text: str | None = None) -> InterviewPrepQuestion | None:
        question = await self.get_question(question_id)
        if not question:
            return None

        if text is not None:
            question.text = text

        await self._session.flush()
        return question

    async def delete_question(self, question_id: int) -> bool:
        question = await self.get_question(question_id)
        if not question:
            return False
        await self._session.delete(question)
        await self._session.flush()
        return True

    async def link_story(self, question_id: int, story_id: int, priority: int = 5) -> InterviewPrepQuestionStory | None:
        question = await self.get_question(question_id)
        if not question:
            return None

        stmt = select(InterviewPrepQuestionStory).where(
            (InterviewPrepQuestionStory.question_id == question_id)
            & (InterviewPrepQuestionStory.story_id == story_id)
        )
        existing = await self._session.scalar(stmt)
        if existing:
            existing.priority = priority
            await self._session.flush()
            return existing

        link = InterviewPrepQuestionStory(question_id=question_id, story_id=story_id, priority=priority)
        self._session.add(link)
        await self._session.flush()
        return link

    async def unlink_story(self, question_id: int, story_id: int) -> bool:
        stmt = delete(InterviewPrepQuestionStory).where(
            (InterviewPrepQuestionStory.question_id == question_id)
            & (InterviewPrepQuestionStory.story_id == story_id)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def update_story_priority(self, question_id: int, story_id: int, priority: int) -> bool:
        stmt = select(InterviewPrepQuestionStory).where(
            (InterviewPrepQuestionStory.question_id == question_id)
            & (InterviewPrepQuestionStory.story_id == story_id)
        )
        link = await self._session.scalar(stmt)
        if not link:
            return False

        link.priority = priority
        await self._session.flush()
        return True
