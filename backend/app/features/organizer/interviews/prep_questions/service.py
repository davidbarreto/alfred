import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.prep_questions.repository import InterviewPrepQuestionRepository
from app.features.organizer.interviews.prep_questions.schemas import (
    InterviewPrepQuestionCreate,
    InterviewPrepQuestionRead,
    InterviewPrepQuestionUpdate,
    InterviewPrepQuestionWithStories,
    InterviewStoryForQuestion,
    StoryLinkRead,
)
from app.features.organizer.interviews.stories.schemas import InterviewStoryTagRead

logger = logging.getLogger(__name__)


class InterviewPrepQuestionService:
    def __init__(self, session: AsyncSession):
        self._repo = InterviewPrepQuestionRepository(session)

    async def get_question(self, question_id: int) -> InterviewPrepQuestionRead | None:
        question = await self._repo.get_question(question_id)
        return InterviewPrepQuestionRead.model_validate(question) if question else None

    async def get_question_with_stories(self, question_id: int) -> InterviewPrepQuestionWithStories | None:
        question = await self._repo.get_question_with_links(question_id)
        if question is None:
            return None
        links = sorted(question.story_links, key=lambda l: (-l.fit_score, -l.story.strength, l.story_id))
        return InterviewPrepQuestionWithStories(
            id=question.id,
            text=question.text,
            created_at=question.created_at,
            updated_at=question.updated_at,
            stories=[
                InterviewStoryForQuestion(
                    id=link.story.id,
                    situation=link.story.situation,
                    task=link.story.task,
                    action=link.story.action,
                    result=link.story.result,
                    strength=link.story.strength,
                    tags=[InterviewStoryTagRead.model_validate(t) for t in link.story.tags],
                    fit_score=link.fit_score,
                )
                for link in links
            ],
        )

    async def get_questions(self, limit: int = 100, offset: int = 0) -> list[InterviewPrepQuestionRead]:
        questions = await self._repo.get_questions(limit=limit, offset=offset)
        return [InterviewPrepQuestionRead.model_validate(q) for q in questions]

    async def create_question(self, data: InterviewPrepQuestionCreate) -> InterviewPrepQuestionRead:
        question = await self._repo.create_question(text=data.text)
        logger.info("Interview prep question created: id=%d", question.id)
        return InterviewPrepQuestionRead.model_validate(question)

    async def update_question(
        self, question_id: int, data: InterviewPrepQuestionUpdate
    ) -> InterviewPrepQuestionRead | None:
        question = await self._repo.update_question(question_id=question_id, text=data.text)
        if question is None:
            logger.debug("Interview prep question update: id=%d not found", question_id)
            return None
        logger.info("Interview prep question updated: id=%d fields=%s", question_id, list(data.model_dump(exclude_unset=True)))
        return InterviewPrepQuestionRead.model_validate(question)

    async def delete_question(self, question_id: int) -> bool:
        deleted = await self._repo.delete_question(question_id)
        if deleted:
            logger.info("Interview prep question deleted: id=%d", question_id)
        return deleted

    async def link_story(self, question_id: int, story_id: int, fit_score: int) -> StoryLinkRead | None:
        """Create the link, or update its fit_score if it already exists. None if either side is missing."""
        if await self._repo.get_question(question_id) is None or not await self._repo.story_exists(story_id):
            logger.debug("Story link: question_id=%d or story_id=%d not found", question_id, story_id)
            return None
        link = await self._repo.link_story(question_id, story_id, fit_score)
        logger.info("Story linked to prep question: question_id=%d story_id=%d fit_score=%d", question_id, story_id, fit_score)
        return StoryLinkRead.model_validate(link)

    async def unlink_story(self, question_id: int, story_id: int) -> bool:
        unlinked = await self._repo.unlink_story(question_id, story_id)
        if unlinked:
            logger.info("Story unlinked from prep question: question_id=%d story_id=%d", question_id, story_id)
        return unlinked
