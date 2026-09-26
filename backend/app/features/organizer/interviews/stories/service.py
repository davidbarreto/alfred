import logging
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.stories.repository import InterviewStoryRepository
from app.features.organizer.interviews.stories.schemas import InterviewStoryCreate, InterviewStoryUpdate
from app.features.organizer.interviews.stories.tables import InterviewStory
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


class InterviewStoryService:
    def __init__(self, session: AsyncSession, llm_provider: LlmProvider | None = None):
        self._repo = InterviewStoryRepository(session)
        self._llm_provider = llm_provider

    async def get_story(self, story_id: int) -> InterviewStory | None:
        return await self._repo.get_story(story_id)

    async def get_stories(self, limit: int = 100, offset: int = 0) -> list[InterviewStory]:
        return await self._repo.get_stories(limit=limit, offset=offset)

    async def get_stories_by_tag(self, tag: str, limit: int = 100, offset: int = 0) -> list[InterviewStory]:
        return await self._repo.get_stories_by_tag(tag=tag, limit=limit, offset=offset)

    async def create_story(self, data: InterviewStoryCreate) -> InterviewStory:
        story = await self._repo.create_story(
            situation=data.situation,
            task=data.task,
            action=data.action,
            result=data.result,
            strength=data.strength,
        )
        if data.tags:
            await self._repo.set_tags(story.id, data.tags)
        logger.info("Interview story created: id=%d", story.id)
        return story

    async def update_story(self, story_id: int, data: InterviewStoryUpdate) -> InterviewStory | None:
        story = await self._repo.update_story(
            story_id=story_id,
            situation=data.situation,
            task=data.task,
            action=data.action,
            result=data.result,
            strength=data.strength,
        )
        if not story:
            return None

        if data.tags is not None:
            await self._repo.set_tags(story_id, data.tags)

        logger.info("Interview story updated: id=%d", story_id)
        return story

    async def delete_story(self, story_id: int) -> bool:
        result = await self._repo.delete_story(story_id)
        if result:
            logger.info("Interview story deleted: id=%d", story_id)
        return result

    async def add_tag(self, story_id: int, tag: str) -> bool:
        result = await self._repo.add_tag(story_id, tag)
        if result:
            logger.debug("Tag added to story: story_id=%d tag=%r", story_id, tag)
        return result is not None

    async def remove_tag(self, story_id: int, tag: str) -> bool:
        result = await self._repo.remove_tag(story_id, tag)
        if result:
            logger.debug("Tag removed from story: story_id=%d tag=%r", story_id, tag)
        return result

    async def get_all_tags(self) -> list[str]:
        return await self._repo.get_all_tags()

    async def assess_strength(self, story_id: int) -> int | None:
        if not self._llm_provider:
            return None

        story = await self.get_story(story_id)
        if not story:
            return None

        prompt = f"""Assess the quality of this STAR story on a scale of 1-5:

Situation: {story.situation}

Task: {story.task}

Action: {story.action}

Result: {story.result}

Evaluate based on:
- Clarity of structure (all parts present and clear)
- Level of specific details (vague vs. concrete)
- Measurable outcome (quantified vs. fuzzy)
- Demonstrates key competency or skill
- Authenticity and credibility

Respond with ONLY a JSON object: {{"score": <1-5>}}
"""
        try:
            response = await self._llm_provider.generate(prompt)
            data = json.loads(response.strip())
            score = int(data.get("score", 3))
            return max(1, min(5, score))
        except Exception as e:
            logger.error("Failed to assess story strength: story_id=%d error=%s", story_id, e)
            return None
