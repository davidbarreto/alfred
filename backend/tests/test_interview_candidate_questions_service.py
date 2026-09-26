import pytest
from unittest.mock import AsyncMock

from app.features.organizer.interviews.candidate_questions.service import InterviewCandidateQuestionService
from app.features.organizer.interviews.candidate_questions.schemas import InterviewCandidateQuestionCreate, InterviewCandidateQuestionUpdate
from app.features.organizer.interviews.candidate_questions.tables import InterviewCandidateQuestion


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    service = InterviewCandidateQuestionService(AsyncMock())
    service._repo = mock_repo
    return service


class TestCreateQuestion:
    async def test_create_question(self, service, mock_repo):
        question = InterviewCandidateQuestion(
            id=1,
            text="How is the onboarding process?",
            category="Onboarding",
        )
        mock_repo.create_question.return_value = question

        data = InterviewCandidateQuestionCreate(
            text="How is the onboarding process?",
            category="Onboarding",
        )

        result = await service.create_question(data)

        assert result.id == 1
        assert result.text == "How is the onboarding process?"
        assert result.category == "Onboarding"


class TestUpdateQuestion:
    async def test_update_question(self, service, mock_repo):
        updated_question = InterviewCandidateQuestion(
            id=1,
            text="Updated question",
            category="Tech",
        )
        mock_repo.update_question.return_value = updated_question

        data = InterviewCandidateQuestionUpdate(text="Updated question", category="Tech")

        result = await service.update_question(1, data)

        assert result.category == "Tech"

    async def test_update_question_not_found(self, service, mock_repo):
        mock_repo.update_question.return_value = None

        data = InterviewCandidateQuestionUpdate(text="Updated")

        result = await service.update_question(999, data)

        assert result is None


class TestDeleteQuestion:
    async def test_delete_question(self, service, mock_repo):
        mock_repo.delete_question.return_value = True

        result = await service.delete_question(1)

        assert result is True

    async def test_delete_question_not_found(self, service, mock_repo):
        mock_repo.delete_question.return_value = False

        result = await service.delete_question(999)

        assert result is False


class TestCategories:
    async def test_get_all_categories(self, service, mock_repo):
        mock_repo.get_all_categories.return_value = [
            "Onboarding",
            "Tech",
            "Culture",
            "Benefits",
            "Logistics",
        ]

        result = await service.get_all_categories()

        assert "Onboarding" in result
        assert len(result) == 5


class TestGetQuestionsByCategory:
    async def test_get_questions_by_category(self, service, mock_repo):
        questions = [
            InterviewCandidateQuestion(id=1, text="Q1", category="Tech"),
            InterviewCandidateQuestion(id=2, text="Q2", category="Tech"),
        ]
        mock_repo.get_questions_by_category.return_value = questions

        result = await service.get_questions_by_category("Tech")

        assert len(result) == 2
        mock_repo.get_questions_by_category.assert_called_once_with(category="Tech", limit=100, offset=0)
