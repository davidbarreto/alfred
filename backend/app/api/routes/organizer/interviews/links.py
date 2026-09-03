from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewLinkServiceDep
from app.features.organizer.interviews.links.schemas import InterviewLinkCreate, InterviewLinkRead

router = APIRouter(
    prefix="/organizer/interview-links",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[InterviewLinkRead])
async def get_links(
    service: InterviewLinkServiceDep,
    process_id: int = Query(...),
) -> list[InterviewLinkRead]:
    return await service.get_links(process_id)


@router.post("", response_model=InterviewLinkRead, status_code=status.HTTP_201_CREATED)
async def create_link(request: InterviewLinkCreate, service: InterviewLinkServiceDep) -> InterviewLinkRead:
    return await service.create_link(request)


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(link_id: int, service: InterviewLinkServiceDep) -> Response:
    await service.delete_link(link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
