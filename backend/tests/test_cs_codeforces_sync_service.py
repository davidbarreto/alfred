from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.cs.platforms.codeforces_sync_service import CodeforcesSyncService


def _platform_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.code = "codeforces"
    orm.handle = kwargs.get("handle", "tourist")
    orm.sync_enabled = kwargs.get("sync_enabled", True)
    orm.last_submission_external_id = kwargs.get("last_submission_external_id", None)
    return orm


def _cf_submission(sub_id, verdict="OK", rating=1200, contest_id=100, index="A"):
    return {
        "id": sub_id,
        "creationTimeSeconds": 1700000000,
        "problem": {"contestId": contest_id, "index": index, "name": "Test Problem", "tags": ["dp"], "rating": rating},
        "verdict": verdict,
        "programmingLanguage": "GNU C++17",
    }


def _problem_read(id=1):
    obj = MagicMock()
    obj.id = id
    return obj


def _submission_read(verdict="accepted"):
    obj = MagicMock()
    obj.verdict = verdict
    return obj


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def service(mock_session, mock_client):
    svc = CodeforcesSyncService(session=mock_session, client=mock_client)
    svc._platforms = AsyncMock()
    svc._problems = AsyncMock()
    svc._submissions = AsyncMock()
    svc._plans = AsyncMock()
    return svc


class TestSync:
    async def test_skips_when_platform_not_configured(self, service):
        service._platforms.get_platform_by_code.return_value = None
        result = await service.sync()
        assert result == 0

    async def test_skips_when_no_handle(self, service):
        service._platforms.get_platform_by_code.return_value = _platform_orm(handle=None)
        result = await service.sync()
        assert result == 0

    async def test_skips_submission_without_verdict_yet(self, service, mock_client):
        service._platforms.get_platform_by_code.return_value = _platform_orm()
        mock_client.get_user_info.return_value = {"rating": 3000, "maxRating": 3500, "rank": "grandmaster"}
        in_progress = {
            "id": 5, "creationTimeSeconds": 1700000000,
            "problem": {"contestId": 100, "index": "A", "name": "P", "tags": []},
            "programmingLanguage": "GNU C++17",
        }  # no "verdict" key
        mock_client.get_submissions_since.return_value = [in_progress]

        count = await service.sync()

        assert count == 0
        service._problems.upsert_problem.assert_not_called()

    async def test_ingests_new_submissions_and_advances_watermark(self, service, mock_client):
        service._platforms.get_platform_by_code.return_value = _platform_orm(last_submission_external_id=None)
        mock_client.get_user_info.return_value = {"rating": 3000, "maxRating": 3500, "rank": "grandmaster"}
        mock_client.get_submissions_since.return_value = [
            _cf_submission(102),
            _cf_submission(101),
        ]
        service._problems.upsert_problem.return_value = _problem_read(id=7)
        service._submissions.upsert_submission.return_value = _submission_read(verdict="accepted")

        count = await service.sync()

        assert count == 2
        service._plans.auto_complete_items_for_problem.assert_called_with(7)
        update_call = service._platforms.update_platform.call_args
        assert update_call[0][0] == service._platforms.get_platform_by_code.return_value.id
        assert update_call[0][1].last_submission_external_id == "102"

    async def test_does_not_autocomplete_for_non_accepted_verdict(self, service, mock_client):
        service._platforms.get_platform_by_code.return_value = _platform_orm()
        mock_client.get_user_info.return_value = {"rating": None, "maxRating": None, "rank": None}
        mock_client.get_submissions_since.return_value = [_cf_submission(200, verdict="WRONG_ANSWER")]
        service._problems.upsert_problem.return_value = _problem_read(id=9)
        service._submissions.upsert_submission.return_value = _submission_read(verdict="wrong_answer")

        await service.sync()

        service._plans.auto_complete_items_for_problem.assert_not_called()
