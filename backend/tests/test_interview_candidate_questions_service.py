from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.features.organizer.interviews.candidate_questions.schemas import (
    InterviewCandidateQuestionCreate,
    InterviewCandidateQuestionUpdate,
)
from app.features.organizer.interviews.candidate_questions.service import InterviewCandidateQuestionService
from app.features.organizer.interviews.candidate_questions.tables import InterviewCandidateQuestion

_NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _question(id=1, text="How is the onboarding process?", category="Onboarding") -> InterviewCandidateQuestion:
    return InterviewCandidateQuestion(id=id, text=text, category=category, created_at=_NOW, updated_at=_NOW)


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    svc = InterviewCandidateQuestionService(AsyncMock())
    svc._repo = mock_repo
    return svc


class TestCreateQuestion:
    async def test_returns_read_model(self, service, mock_repo):
        mock_repo.create_question.return_value = _question()

        result = await service.create_question(
            InterviewCandidateQuestionCreate(text="How is the onboarding process?", category="Onboarding")
        )

        assert result.id == 1
        assert result.category == "Onboarding"
        assert result.created_at == _NOW

    def test_text_longer_than_column_is_rejected(self):
        with pytest.raises(ValidationError):
            InterviewCandidateQuestionCreate(text="x" * 501, category="Tech")


class TestUpdateQuestion:
    async def test_passes_only_set_fields(self, service, mock_repo):
        mock_repo.update_question.return_value = _question(category="Tech")

        result = await service.update_question(1, InterviewCandidateQuestionUpdate(category="Tech"))

        assert result is not None and result.category == "Tech"
        mock_repo.update_question.assert_awaited_once_with(1, fields={"category": "Tech"})

    async def test_not_found(self, service, mock_repo):
        mock_repo.update_question.return_value = None
        assert await service.update_question(999, InterviewCandidateQuestionUpdate(text="x")) is None


class TestDeleteQuestion:
    async def test_delete(self, service, mock_repo):
        mock_repo.delete_question.return_value = True
        assert await service.delete_question(1) is True

    async def test_not_found(self, service, mock_repo):
        mock_repo.delete_question.return_value = False
        assert await service.delete_question(999) is False


class TestListing:
    async def test_filters_by_category(self, service, mock_repo):
        mock_repo.get_questions.return_value = [_question(id=1, category="Tech"), _question(id=2, category="Tech")]

        result = await service.get_questions(category="Tech")

        assert len(result) == 2
        mock_repo.get_questions.assert_awaited_once_with(category="Tech", limit=100, offset=0)

    async def test_categories(self, service, mock_repo):
        mock_repo.get_all_categories.return_value = ["Onboarding", "Tech"]
        assert await service.get_all_categories() == ["Onboarding", "Tech"]
