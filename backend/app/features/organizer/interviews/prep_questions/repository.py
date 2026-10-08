from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion, InterviewPrepQuestionStory
from app.features.organizer.interviews.stories.tables import InterviewStory
from app.features.organizer.interviews.tags.repository import InterviewTagRepository
from app.features.organizer.interviews.tags.tables import InterviewTag, interview_question_tag_links


class InterviewPrepQuestionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._tags = InterviewTagRepository(session)

    async def get_question(self, question_id: int) -> InterviewPrepQuestion | None:
        stmt = (
            select(InterviewPrepQuestion)
            .where(InterviewPrepQuestion.id == question_id)
            .options(selectinload(InterviewPrepQuestion.tags))
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_question_with_links(self, question_id: int) -> InterviewPrepQuestion | None:
        stmt = (
            select(InterviewPrepQuestion)
            .where(InterviewPrepQuestion.id == question_id)
            .options(
                selectinload(InterviewPrepQuestion.tags),
                selectinload(InterviewPrepQuestion.story_links)
                .selectinload(InterviewPrepQuestionStory.story)
                .selectinload(InterviewStory.tags)
            )
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_questions(
        self, tag: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[InterviewPrepQuestion]:
        stmt = select(InterviewPrepQuestion).options(selectinload(InterviewPrepQuestion.tags))
        if tag:
            tagged = (
                select(interview_question_tag_links.c.question_id)
                .join(InterviewTag, InterviewTag.id == interview_question_tag_links.c.tag_id)
                .where(func.lower(InterviewTag.name) == tag.lower())
            )
            stmt = stmt.where(InterviewPrepQuestion.id.in_(tagged))
        stmt = (
            stmt.order_by(InterviewPrepQuestion.created_at.desc(), InterviewPrepQuestion.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_story_counts(self, question_ids: list[int]) -> dict[int, int]:
        stmt = (
            select(InterviewPrepQuestionStory.question_id, func.count())
            .where(InterviewPrepQuestionStory.question_id.in_(question_ids))
            .group_by(InterviewPrepQuestionStory.question_id)
        )
        return {question_id: count for question_id, count in (await self._session.execute(stmt)).all()}

    async def create_question(self, text: str, tags: list[str]) -> InterviewPrepQuestion:
        question = InterviewPrepQuestion(text=text, tags=await self._tags.get_or_create_tags(tags))
        self._session.add(question)
        await self._session.commit()
        refreshed = await self.get_question(question.id)
        assert refreshed is not None
        return refreshed

    async def update_question(
        self, question_id: int, text: str | None, tags: list[str] | None
    ) -> InterviewPrepQuestion | None:
        question = await self.get_question(question_id)
        if question is None:
            return None
        if text is not None:
            question.text = text
        if tags is not None:
            question.tags = await self._tags.get_or_create_tags(tags)
        await self._session.commit()
        return await self.get_question(question_id)

    async def add_tag(self, question_id: int, tag: str) -> InterviewPrepQuestion | None:
        question = await self.get_question(question_id)
        if question is None:
            return None
        resolved = (await self._tags.get_or_create_tags([tag]))[0]
        if resolved not in question.tags:
            question.tags.append(resolved)
        await self._session.commit()
        return await self.get_question(question_id)

    async def remove_tag(self, question_id: int, tag: str) -> bool:
        question = await self.get_question(question_id)
        if question is None:
            return False
        matching = [t for t in question.tags if t.name.lower() == tag.lower()]
        if not matching:
            return False
        question.tags = [t for t in question.tags if t not in matching]
        await self._session.commit()
        return True

    async def get_all_tags(self) -> list[str]:
        stmt = (
            select(InterviewTag.name)
            .join(interview_question_tag_links, interview_question_tag_links.c.tag_id == InterviewTag.id)
            .distinct()
            .order_by(InterviewTag.name)
        )
        return list((await self._session.scalars(stmt)).all())

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
