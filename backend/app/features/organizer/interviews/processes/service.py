from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.study_plans.repository import StudyPlanRepository
from app.features.organizer.interviews.companies.repository import CompanyRepository
from app.features.organizer.interviews.processes.repository import InterviewProcessRepository
from app.features.organizer.interviews.processes.schemas import (
    FirstStageInput,
    InterviewProcessCreate,
    InterviewProcessFilters,
    InterviewProcessRead,
    InterviewProcessUpdate,
)
from app.features.organizer.interviews.stages.tables import InterviewStage

logger = logging.getLogger(__name__)


class InterviewProcessService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = InterviewProcessRepository(session)
        self._company_repo = CompanyRepository(session)
        self._study_plan_repo = StudyPlanRepository(session)

    async def get_process(self, process_id: int) -> InterviewProcessRead | None:
        process = await self._repo.get_process(process_id)
        return InterviewProcessRead.model_validate(process) if process else None

    async def get_processes(self, filters: InterviewProcessFilters) -> list[InterviewProcessRead]:
        processes = await self._repo.get_processes(filters)
        return [InterviewProcessRead.model_validate(p) for p in processes]

    async def _validate_refs(self, data: InterviewProcessCreate | InterviewProcessUpdate) -> None:
        if data.company_id is not None:
            company = await self._company_repo.get_company(data.company_id)
            if company is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        if data.study_plan_id is not None:
            plan = await self._study_plan_repo.get_plan(data.study_plan_id)
            if plan is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found")

    async def create_process(self, data: InterviewProcessCreate) -> InterviewProcessRead:
        await self._validate_refs(data)
        process = await self._repo.create_process(data)
        logger.info("Interview process created: id=%d company_id=%d role_title=%r", process.id, process.company_id, process.role_title)
        return InterviewProcessRead.model_validate(process)

    async def create_process_with_optional_first_stage(
        self, data: InterviewProcessCreate, first_stage: FirstStageInput | None
    ) -> InterviewProcessRead:
        await self._validate_refs(data)
        stage = None
        if first_stage is not None:
            stage = InterviewStage(stage_type=first_stage.stage_type, scheduled_at=first_stage.scheduled_at)
        process = await self._repo.create_process(data, first_stage=stage)
        logger.info(
            "Interview process created: id=%d company_id=%d role_title=%r with_first_stage=%s",
            process.id, process.company_id, process.role_title, first_stage is not None,
        )
        return InterviewProcessRead.model_validate(process)

    async def update_process(self, process_id: int, data: InterviewProcessUpdate) -> InterviewProcessRead | None:
        await self._validate_refs(data)
        process = await self._repo.update_process(process_id, data)
        if process is None:
            logger.debug("Interview process update: id=%d not found", process_id)
            return None
        logger.info("Interview process updated: id=%d fields=%s", process_id, list(data.model_dump(exclude_unset=True).keys()))
        return InterviewProcessRead.model_validate(process)

    async def delete_process(self, process_id: int) -> None:
        await self._repo.delete_process(process_id)
        logger.info("Interview process deleted: id=%d", process_id)
