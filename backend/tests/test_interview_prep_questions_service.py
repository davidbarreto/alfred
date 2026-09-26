import pytest
from unittest.mock import AsyncMock

from app.features.organizer.interviews.prep_questions.service import InterviewPrepQuestionService
from app.features.organizer.interviews.prep_questions.schemas import InterviewPrepQuestionCreate, InterviewPrepQuestionUpdate
from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion, InterviewPrepQuestionStory


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    service = InterviewPrepQuestionService(AsyncMock())
    service._repo = mock_repo
    return service


class TestCreateQuestion:
    async def test_create_question(self, service, mock_repo):
        question = InterviewPrepQuestion(
            id=1,
            text="Tell me about a difficult decision",
        )
        mock_repo.create_question.return_value = question

        data = InterviewPrepQuestionCreate(text="Tell me about a difficult decision")

        result = await service.create_question(data)

        assert result.id == 1
        assert result.text == "Tell me about a difficult decision"
        mock_repo.create_question.assert_called_once_with(text="Tell me about a difficult decision")


class TestUpdateQuestion:
    async def test_update_question(self, service, mock_repo):
        updated_question = InterviewPrepQuestion(
            id=1,
            text="Updated question",
        )
        mock_repo.update_question.return_value = updated_question

        data = InterviewPrepQuestionUpdate(text="Updated question")

        result = await service.update_question(1, data)

        assert result.text == "Updated question"

    async def test_update_question_not_found(self, service, mock_repo):
        mock_repo.update_question.return_value = None

        data = InterviewPrepQuestionUpdate(text="Updated")

        result = await service.update_question(999, data)

        assert result is None


class TestLinkStory:
    async def test_link_story(self, service, mock_repo):
        link = InterviewPrepQuestionStory(
            id=1,
            story_id=1,
            question_id=1,
            priority=5,
        )
        mock_repo.link_story.return_value = link

        result = await service.link_story(1, 1, priority=5)

        assert result is True
        mock_repo.link_story.assert_called_once_with(1, 1, 5)

    async def test_link_story_question_not_found(self, service, mock_repo):
        mock_repo.link_story.return_value = None

        result = await service.link_story(999, 1)

        assert result is False


class TestUnlinkStory:
    async def test_unlink_story(self, service, mock_repo):
        mock_repo.unlink_story.return_value = True

        result = await service.unlink_story(1, 1)

        assert result is True

    async def test_unlink_story_not_found(self, service, mock_repo):
        mock_repo.unlink_story.return_value = False

        result = await service.unlink_story(999, 999)

        assert result is False


class TestUpdatePriority:
    async def test_update_story_priority(self, service, mock_repo):
        mock_repo.update_story_priority.return_value = True

        result = await service.update_story_priority(1, 1, 3)

        assert result is True
        mock_repo.update_story_priority.assert_called_once_with(1, 1, 3)
