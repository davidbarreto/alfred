from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import MetricTagServiceDep
from app.features.metrics.tags.schemas import MetricTagRead, MetricTagUpdate, MetricTagUsage
from app.features.metrics.tags.service import MetricTagInUseError, MetricTagNameTakenError

router = APIRouter(
    prefix="/metrics/tags",
    tags=["metrics"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[MetricTagUsage])
async def get_tags(service: MetricTagServiceDep) -> list[MetricTagUsage]:
    return await service.get_tags()


@router.patch("/{tag_id}", response_model=MetricTagRead)
async def rename_tag(tag_id: int, request: MetricTagUpdate, service: MetricTagServiceDep) -> MetricTagRead:
    try:
        tag = await service.rename_tag(tag_id, request)
    except MetricTagNameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A tag with that name already exists")
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, service: MetricTagServiceDep) -> Response:
    try:
        deleted = await service.delete_tag(tag_id)
    except MetricTagInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Tag is used by {exc.entry_count} entries"
        )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
