from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewCompanyServiceDep
from app.features.organizer.interviews.companies.schemas import (
    CompanyCreate,
    CompanyFilters,
    CompanyRead,
    CompanyUpdate,
)

router = APIRouter(
    prefix="/organizer/interview-companies",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[CompanyRead])
async def get_companies(
    service: InterviewCompanyServiceDep,
    filters: CompanyFilters = Depends(),
) -> list[CompanyRead]:
    return await service.get_companies(filters)


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(company_id: int, service: InterviewCompanyServiceDep) -> CompanyRead:
    company = await service.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(request: CompanyCreate, service: InterviewCompanyServiceDep) -> CompanyRead:
    return await service.create_company(request)


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: int, request: CompanyUpdate, service: InterviewCompanyServiceDep
) -> CompanyRead:
    company = await service.update_company(company_id, request)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(company_id: int, service: InterviewCompanyServiceDep) -> Response:
    await service.delete_company(company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
