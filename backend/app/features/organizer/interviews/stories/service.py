import json
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.stories.prompts import STORY_STRENGTH_SYSTEM_PROMPT
from app.features.organizer.interviews.stories.repository import InterviewStoryRepository
from app.features.organizer.interviews.stories.schemas import (
    InterviewStoryCreate,
    InterviewStoryRead,
    InterviewStoryUpdate,
    StoryStrengthAssessment,
)
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


class StoryAssessmentError(Exception):
    """The LLM call failed or returned something that isn't a valid 1-5 assessment."""


class InterviewStoryService:
    def __init__(self, session: AsyncSession, llm_provider: LlmProvider):
        self._session = session
        self._repo = InterviewStoryRepository(session)
        self._llm_provider = llm_provider

    async def get_story(self, story_id: int) -> InterviewStoryRead | None:
        story = await self._repo.get_story(story_id)
        return InterviewStoryRead.model_validate(story) if story else None

    async def get_stories(
        self, tag: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[InterviewStoryRead]:
        if tag:
            stories = await self._repo.get_stories_by_tag(tag, limit=limit, offset=offset)
        else:
            stories = await self._repo.get_stories(limit=limit, offset=offset)
        return [InterviewStoryRead.model_validate(s) for s in stories]

    async def search_stories(self, query: str, limit: int = 20) -> list[InterviewStoryRead]:
        stories = await self._repo.search_stories(query, limit=limit)
        return [InterviewStoryRead.model_validate(s) for s in stories]

    async def create_story(self, data: InterviewStoryCreate) -> InterviewStoryRead:
        story = await self._repo.create_story(
            situation=data.situation,
            task=data.task,
            action=data.action,
            result=data.result,
            strength=data.strength,
            tags=data.tags,
        )
        logger.info("Interview story created: id=%d strength=%d tags=%d", story.id, story.strength, len(data.tags))
        return InterviewStoryRead.model_validate(story)

    async def update_story(self, story_id: int, data: InterviewStoryUpdate) -> InterviewStoryRead | None:
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        tags = changes.pop("tags", None)
        story = await self._repo.update_story(story_id, fields=changes, tags=tags)
        if story is None:
            logger.debug("Interview story update: id=%d not found", story_id)
            return None
        logger.info("Interview story updated: id=%d fields=%s", story_id, [*changes, *(["tags"] if tags is not None else [])])
        return InterviewStoryRead.model_validate(story)

    async def delete_story(self, story_id: int) -> bool:
        deleted = await self._repo.delete_story(story_id)
        if deleted:
            logger.info("Interview story deleted: id=%d", story_id)
        return deleted

    async def add_tag(self, story_id: int, tag: str) -> InterviewStoryRead | None:
        story = await self._repo.add_tag(story_id, tag.strip())
        if story is None:
            return None
        logger.info("Interview story tagged: id=%d tag=%r", story_id, tag)
        return InterviewStoryRead.model_validate(story)

    async def remove_tag(self, story_id: int, tag: str) -> bool:
        removed = await self._repo.remove_tag(story_id, tag)
        if removed:
            logger.info("Interview story tag removed: id=%d tag=%r", story_id, tag)
        return removed

    async def get_all_tags(self) -> list[str]:
        return await self._repo.get_all_tags()

    async def assess_strength(self, story_id: int) -> StoryStrengthAssessment | None:
        story = await self._repo.get_story(story_id)
        if story is None:
            return None

        messages = [{
            "role": "user",
            "content": (
                f"Situation: {story.situation}\n\nTask: {story.task}\n\n"
                f"Action: {story.action}\n\nResult: {story.result}"
            ),
        }]
        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages, system=STORY_STRENGTH_SYSTEM_PROMPT)
        except Exception as exc:
            logger.error("Story strength assessment failed: story_id=%d error=%s", story_id, exc)
            raise StoryAssessmentError("LLM call failed") from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="interview_story_strength",
            prompt=messages,
            response=raw,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            finish_reason=llm_response.finish_reason,
            latency_ms=latency_ms,
        )

        try:
            parsed = json.loads(raw)
            assessment = StoryStrengthAssessment(
                story_id=story_id,
                suggested_strength=int(parsed["score"]),
                reasoning=str(parsed.get("reasoning", "")),
            )
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Story strength assessment: invalid LLM output story_id=%d raw=%r", story_id, raw[:200])
            raise StoryAssessmentError("LLM returned an invalid assessment") from exc

        logger.info(
            "Story strength assessed: story_id=%d suggested=%d current=%d",
            story_id, assessment.suggested_strength, story.strength,
        )
        return assessment
