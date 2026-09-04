from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.features.organizer.interviews.processes.jd_extraction_service import (
    JdExtractionService,
    JobPostingExtraction,
)
from app.features.organizer.interviews.processes.schemas import (
    FirstStageInput,
    InterviewProcessCreate,
    InterviewProcessFilters,
    InterviewProcessUpdate,
)
from app.features.organizer.interviews.processes.service import InterviewProcessService
from app.shared.llm import LlmResponse


def _make_process_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.company_id = kwargs.get("company_id", 1)
    orm.role_title = kwargs.get("role_title", "Backend Engineer")
    orm.status = kwargs.get("status", "active")
    orm.source = None
    orm.applied_date = None
    orm.priority = None
    orm.department = None
    orm.notes = None
    orm.study_plan_id = kwargs.get("study_plan_id", None)
    orm.salary_min = None
    orm.salary_max = None
    orm.salary_currency = None
    orm.work_regime = None
    orm.office_days_per_month = None
    orm.office_location = None
    orm.benefits = None
    orm.job_description_url = None
    orm.company_feedback = None
    orm.stages = kwargs.get("stages", [])
    orm.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    orm.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return orm


@pytest.fixture
def service():
    svc = InterviewProcessService(session=AsyncMock())
    svc._repo = AsyncMock()
    svc._company_repo = AsyncMock()
    svc._study_plan_repo = AsyncMock()
    return svc


class TestCreateProcess:
    async def test_raises_404_when_company_missing(self, service):
        service._company_repo.get_company.return_value = None
        data = InterviewProcessCreate(company_id=999, role_title="Backend Engineer")
        with pytest.raises(HTTPException) as exc:
            await service.create_process(data)
        assert exc.value.status_code == 404
        service._repo.create_process.assert_not_called()

    async def test_raises_404_when_study_plan_missing(self, service):
        service._company_repo.get_company.return_value = MagicMock()
        service._study_plan_repo.get_plan.return_value = None
        data = InterviewProcessCreate(company_id=1, role_title="Backend Engineer", study_plan_id=999)
        with pytest.raises(HTTPException) as exc:
            await service.create_process(data)
        assert exc.value.status_code == 404

    async def test_delegates_to_repo_when_valid(self, service):
        service._company_repo.get_company.return_value = MagicMock()
        service._repo.create_process.return_value = _make_process_orm()
        data = InterviewProcessCreate(company_id=1, role_title="Backend Engineer")
        result = await service.create_process(data)
        service._repo.create_process.assert_called_once_with(data)
        assert result.role_title == "Backend Engineer"


class TestCreateProcessWithOptionalFirstStage:
    async def test_creates_process_without_stage(self, service):
        service._company_repo.get_company.return_value = MagicMock()
        service._repo.create_process.return_value = _make_process_orm()
        data = InterviewProcessCreate(company_id=1, role_title="Backend Engineer")
        await service.create_process_with_optional_first_stage(data, None)
        _, kwargs = service._repo.create_process.call_args
        assert kwargs.get("first_stage") is None

    async def test_creates_process_with_stage(self, service):
        service._company_repo.get_company.return_value = MagicMock()
        service._repo.create_process.return_value = _make_process_orm()
        data = InterviewProcessCreate(company_id=1, role_title="Backend Engineer")
        first_stage = FirstStageInput(stage_type="phone_screen")
        await service.create_process_with_optional_first_stage(data, first_stage)
        _, kwargs = service._repo.create_process.call_args
        assert kwargs.get("first_stage") is not None
        assert kwargs["first_stage"].stage_type == "phone_screen"


class TestUpdateProcess:
    async def test_returns_none_when_not_found(self, service):
        service._repo.update_process.return_value = None
        result = await service.update_process(999, InterviewProcessUpdate(role_title="New"))
        assert result is None


class TestGetProcesses:
    async def test_returns_processes_from_repo(self, service):
        service._repo.get_processes.return_value = [_make_process_orm(id=1), _make_process_orm(id=2)]
        filters = InterviewProcessFilters(limit=50, offset=0, company_id=None, status=None)
        result = await service.get_processes(filters)
        service._repo.get_processes.assert_called_once_with(filters)
        assert [p.id for p in result] == [1, 2]


class TestDeleteProcess:
    async def test_delegates_to_repo(self, service):
        await service.delete_process(1)
        service._repo.delete_process.assert_called_once_with(1)


class TestJdExtractionService:
    @pytest.fixture
    def jd_service(self):
        llm_provider = MagicMock()
        llm_provider.provider = "google"
        llm_provider.model = "gemini-test"
        llm_provider.complete = AsyncMock()
        svc = JdExtractionService(session=AsyncMock(), llm_provider=llm_provider)
        return svc, llm_provider

    async def test_extracts_fields_and_logs_llm_call(self, jd_service):
        svc, llm_provider = jd_service
        llm_provider.complete.return_value = LlmResponse(
            text='{"role_title": "Backend Engineer", "company_name": "Acme", "office_days_per_month": 8.0}',
            tokens_input=100,
            tokens_output=20,
            finish_reason="STOP",
        )
        fake_response = MagicMock()
        fake_response.text = "<html><body>Backend Engineer at Acme, 2 days a week onsite</body></html>"
        fake_response.raise_for_status = MagicMock()

        with patch("app.features.organizer.interviews.processes.jd_extraction_service.requests.get", return_value=fake_response), \
             patch("app.features.organizer.interviews.processes.jd_extraction_service.create_llm_call", new=AsyncMock()) as mock_log:
            result = await svc.extract_from_url("https://example.com/job/123")

        assert isinstance(result, JobPostingExtraction)
        assert result.role_title == "Backend Engineer"
        assert result.company_name == "Acme"
        assert result.office_days_per_month == 8.0
        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["feature"] == "interview_jd_extraction"

    async def test_strips_markdown_code_fences(self, jd_service):
        svc, llm_provider = jd_service
        llm_provider.complete.return_value = LlmResponse(
            text='```json\n{"role_title": "Backend Engineer"}\n```',
            tokens_input=10,
            tokens_output=5,
            finish_reason="STOP",
        )
        fake_response = MagicMock()
        fake_response.text = "<html></html>"
        fake_response.raise_for_status = MagicMock()

        with patch("app.features.organizer.interviews.processes.jd_extraction_service.requests.get", return_value=fake_response), \
             patch("app.features.organizer.interviews.processes.jd_extraction_service.create_llm_call", new=AsyncMock()):
            result = await svc.extract_from_url("https://example.com/job/123")

        assert result.role_title == "Backend Engineer"
