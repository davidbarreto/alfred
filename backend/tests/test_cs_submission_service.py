from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.cs.submissions.schemas import SubmissionCreate, SubmissionFilters
from app.features.cs.submissions.service import SubmissionService


def _make_submission_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.platform_id = kwargs.get("platform_id", 1)
    orm.problem_id = kwargs.get("problem_id", 1)
    orm.external_id = kwargs.get("external_id", "999")
    orm.verdict = kwargs.get("verdict", "accepted")
    orm.verdict_raw = kwargs.get("verdict_raw", "OK")
    orm.language = kwargs.get("language", "cpp")
    orm.language_raw = kwargs.get("language_raw", "GNU C++17")
    orm.source_method = kwargs.get("source_method", "api_sync")
    orm.submitted_at = kwargs.get("submitted_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    orm.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    orm.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return orm


@pytest.fixture
def service():
    svc = SubmissionService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestCreateSubmission:
    async def test_creates_and_returns_read(self, service):
        service._repo.create_submission.return_value = _make_submission_orm(verdict="wrong_answer")
        data = SubmissionCreate(
            platform_id=1, problem_id=1, external_id="1", verdict="wrong_answer",
            submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        result = await service.create_submission(data)
        assert result.verdict == "wrong_answer"


class TestUpsertSubmission:
    async def test_delegates_to_repo(self, service):
        service._repo.upsert_submission.return_value = _make_submission_orm(external_id="42")
        data = SubmissionCreate(
            platform_id=1, problem_id=1, external_id="42", verdict="accepted",
            submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        result = await service.upsert_submission(data)
        service._repo.upsert_submission.assert_called_once_with(data)
        assert result.external_id == "42"


class TestGetSubmissions:
    async def test_filters_by_verdict(self, service):
        service._repo.get_submissions.return_value = [_make_submission_orm(verdict="accepted")]
        result = await service.get_submissions(SubmissionFilters(verdict="accepted"))
        assert len(result) == 1
        assert result[0].verdict == "accepted"
