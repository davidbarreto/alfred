from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.stories.tables import InterviewStory, InterviewStoryTag


class InterviewStoryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_story(self, story_id: int) -> InterviewStory | None:
        stmt = select(InterviewStory).where(InterviewStory.id == story_id)
        return await self._session.scalar(stmt)

    async def get_stories(self, limit: int = 100, offset: int = 0) -> list[InterviewStory]:
        stmt = select(InterviewStory).order_by(InterviewStory.created_at.desc()).limit(limit).offset(offset)
        return await self._session.scalars(stmt)

    async def get_stories_by_tag(self, tag: str, limit: int = 100, offset: int = 0) -> list[InterviewStory]:
        stmt = (
            select(InterviewStory)
            .join(InterviewStoryTag)
            .where(InterviewStoryTag.tag == tag)
            .distinct()
            .order_by(InterviewStory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return await self._session.scalars(stmt)

    async def create_story(self, situation: str, task: str, action: str, result: str, strength: int) -> InterviewStory:
        story = InterviewStory(situation=situation, task=task, action=action, result=result, strength=strength)
        self._session.add(story)
        await self._session.flush()
        return story

    async def update_story(
        self, story_id: int, situation: str | None = None, task: str | None = None,
        action: str | None = None, result: str | None = None, strength: int | None = None
    ) -> InterviewStory | None:
        story = await self.get_story(story_id)
        if not story:
            return None

        if situation is not None:
            story.situation = situation
        if task is not None:
            story.task = task
        if action is not None:
            story.action = action
        if result is not None:
            story.result = result
        if strength is not None:
            story.strength = strength

        await self._session.flush()
        return story

    async def delete_story(self, story_id: int) -> bool:
        story = await self.get_story(story_id)
        if not story:
            return False
        await self._session.delete(story)
        await self._session.flush()
        return True

    async def add_tag(self, story_id: int, tag: str) -> InterviewStoryTag | None:
        story = await self.get_story(story_id)
        if not story:
            return None

        stmt = select(InterviewStoryTag).where(
            (InterviewStoryTag.story_id == story_id) & (InterviewStoryTag.tag == tag)
        )
        existing = await self._session.scalar(stmt)
        if existing:
            return existing

        tag_obj = InterviewStoryTag(story_id=story_id, tag=tag)
        self._session.add(tag_obj)
        await self._session.flush()
        return tag_obj

    async def remove_tag(self, story_id: int, tag: str) -> bool:
        stmt = delete(InterviewStoryTag).where(
            (InterviewStoryTag.story_id == story_id) & (InterviewStoryTag.tag == tag)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def set_tags(self, story_id: int, tags: list[str]) -> None:
        await self._session.execute(
            delete(InterviewStoryTag).where(InterviewStoryTag.story_id == story_id)
        )
        for tag in tags:
            self._session.add(InterviewStoryTag(story_id=story_id, tag=tag))
        await self._session.flush()

    async def get_all_tags(self) -> list[str]:
        stmt = select(InterviewStoryTag.tag).distinct().order_by(InterviewStoryTag.tag)
        result = await self._session.scalars(stmt)
        return list(result)
