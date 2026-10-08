from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.interviews.stories.tables import InterviewStory
from app.features.organizer.interviews.tags.repository import InterviewTagRepository
from app.features.organizer.interviews.tags.tables import InterviewTag, interview_story_tag_links


class InterviewStoryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._tags = InterviewTagRepository(session)

    async def get_story(self, story_id: int) -> InterviewStory | None:
        stmt = (
            select(InterviewStory)
            .where(InterviewStory.id == story_id)
            .options(selectinload(InterviewStory.tags))
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_stories(self, limit: int = 100, offset: int = 0) -> list[InterviewStory]:
        stmt = (
            select(InterviewStory)
            .options(selectinload(InterviewStory.tags))
            .order_by(InterviewStory.created_at.desc(), InterviewStory.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_stories_by_tag(self, tag: str, limit: int = 100, offset: int = 0) -> list[InterviewStory]:
        tagged = (
            select(interview_story_tag_links.c.story_id)
            .join(InterviewTag, InterviewTag.id == interview_story_tag_links.c.tag_id)
            .where(func.lower(InterviewTag.name) == tag.lower())
        )
        stmt = (
            select(InterviewStory)
            .where(InterviewStory.id.in_(tagged))
            .options(selectinload(InterviewStory.tags))
            .order_by(InterviewStory.created_at.desc(), InterviewStory.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def search_stories(self, query: str, limit: int = 20) -> list[InterviewStory]:
        pattern = f"%{query}%"
        tagged = (
            select(interview_story_tag_links.c.story_id)
            .join(InterviewTag, InterviewTag.id == interview_story_tag_links.c.tag_id)
            .where(InterviewTag.name.ilike(pattern))
        )
        stmt = (
            select(InterviewStory)
            .where(
                or_(
                    InterviewStory.situation.ilike(pattern),
                    InterviewStory.task.ilike(pattern),
                    InterviewStory.action.ilike(pattern),
                    InterviewStory.result.ilike(pattern),
                    InterviewStory.id.in_(tagged),
                )
            )
            .options(selectinload(InterviewStory.tags))
            .order_by(InterviewStory.strength.desc(), InterviewStory.created_at.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def create_story(
        self, situation: str, task: str, action: str, result: str, strength: int, tags: list[str]
    ) -> InterviewStory:
        story = InterviewStory(
            situation=situation,
            task=task,
            action=action,
            result=result,
            strength=strength,
            tags=await self._tags.get_or_create_tags(tags),
        )
        self._session.add(story)
        await self._session.commit()
        refreshed = await self.get_story(story.id)
        assert refreshed is not None
        return refreshed

    async def update_story(
        self, story_id: int, fields: dict[str, Any], tags: list[str] | None
    ) -> InterviewStory | None:
        story = await self.get_story(story_id)
        if story is None:
            return None

        for name, value in fields.items():
            setattr(story, name, value)

        if tags is not None:
            story.tags = await self._tags.get_or_create_tags(tags)

        await self._session.commit()
        return await self.get_story(story_id)

    async def delete_story(self, story_id: int) -> bool:
        story = await self._session.get(InterviewStory, story_id)
        if story is None:
            return False
        await self._session.delete(story)
        await self._session.commit()
        return True

    async def add_tag(self, story_id: int, tag: str) -> InterviewStory | None:
        story = await self.get_story(story_id)
        if story is None:
            return None
        resolved = (await self._tags.get_or_create_tags([tag]))[0]
        if resolved not in story.tags:
            story.tags.append(resolved)
        await self._session.commit()
        return await self.get_story(story_id)

    async def remove_tag(self, story_id: int, tag: str) -> bool:
        story = await self.get_story(story_id)
        if story is None:
            return False
        matching = [t for t in story.tags if t.name.lower() == tag.lower()]
        if not matching:
            return False
        story.tags = [t for t in story.tags if t not in matching]
        await self._session.commit()
        return True

    async def get_all_tags(self) -> list[str]:
        stmt = (
            select(InterviewTag.name)
            .join(interview_story_tag_links, interview_story_tag_links.c.tag_id == InterviewTag.id)
            .distinct()
            .order_by(InterviewTag.name)
        )
        return list((await self._session.scalars(stmt)).all())
