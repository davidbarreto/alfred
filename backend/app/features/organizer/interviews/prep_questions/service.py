import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.prep_questions.repository import InterviewPrepQuestionRepository
from app.features.organizer.interviews.prep_questions.schemas import InterviewPrepQuestionCreate, InterviewPrepQuestionUpdate
from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion

logger = logging.getLogger(__name__)


class InterviewPrepQuestionService:
    def __init__(self, session: AsyncSession):
        self._repo = InterviewPrepQuestionRepository(session)

    async def get_question(self, question_id: int) -> InterviewPrepQuestion | None:
        return await self._repo.get_question(question_id)

    async def get_question_with_stories(self, question_id: int) -> InterviewPrepQuestion | None:
        return await self._repo.get_question_with_stories(question_id)

    async def get_questions(self, limit: int = 100, offset: int = 0) -> list[InterviewPrepQuestion]:
        return await self._repo.get_questions(limit=limit, offset=offset)

    async def create_question(self, data: InterviewPrepQuestionCreate) -> InterviewPrepQuestion:
        question = await self._repo.create_question(text=data.text)
        logger.info("Interview prep question created: id=%d", question.id)
        return question

    async def update_question(self, question_id: int, data: InterviewPrepQuestionUpdate) -> InterviewPrepQuestion | None:
        question = await self._repo.update_question(question_id=question_id, text=data.text)
        if question:
            logger.info("Interview prep question updated: id=%d", question_id)
        return question

    async def delete_question(self, question_id: int) -> bool:
        result = await self._repo.delete_question(question_id)
        if result:
            logger.info("Interview prep question deleted: id=%d", question_id)
        return result

    async def link_story(self, question_id: int, story_id: int, priority: int = 5) -> bool:
        result = await self._repo.link_story(question_id, story_id, priority)
        if result:
            logger.debug("Story linked to prep question: question_id=%d story_id=%d priority=%d", question_id, story_id, priority)
        return result is not None

    async def unlink_story(self, question_id: int, story_id: int) -> bool:
        result = await self._repo.unlink_story(question_id, story_id)
        if result:
            logger.debug("Story unlinked from prep question: question_id=%d story_id=%d", question_id, story_id)
        return result

    async def update_story_priority(self, question_id: int, story_id: int, priority: int) -> bool:
        return await self._repo.update_story_priority(question_id, story_id, priority)
