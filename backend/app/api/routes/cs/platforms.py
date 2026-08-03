import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CodeforcesSyncServiceDep, CsPlatformServiceDep, LeetCodeSyncServiceDep
from app.features.cs.platforms.schemas import PlatformCreate, PlatformFilters, PlatformRead, PlatformUpdate

router = APIRouter(prefix="/cs/platforms", tags=["cs"], dependencies=[Depends(require_auth)])


def _already_refreshed_today(refreshed_at: datetime.datetime | None) -> bool:
    if refreshed_at is None:
        return False
    return refreshed_at.astimezone(datetime.timezone.utc).date() == datetime.datetime.now(
        datetime.timezone.utc
    ).date()


@router.post("", response_model=PlatformRead, status_code=status.HTTP_201_CREATED)
async def create_platform(request: PlatformCreate, service: CsPlatformServiceDep):
    return await service.create_platform(request)


@router.get("", response_model=list[PlatformRead])
async def get_platforms(service: CsPlatformServiceDep, filters: PlatformFilters = Depends()):
    return await service.get_platforms(filters)


@router.get("/{platform_id}", response_model=PlatformRead)
async def get_platform(platform_id: int, service: CsPlatformServiceDep):
    platform = await service.get_platform(platform_id)
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    return platform


@router.patch("/{platform_id}", response_model=PlatformRead)
async def update_platform(platform_id: int, request: PlatformUpdate, service: CsPlatformServiceDep):
    platform = await service.update_platform(platform_id, request)
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    return platform


@router.post("/codeforces/sync")
async def sync_codeforces(service: CodeforcesSyncServiceDep) -> dict[str, int]:
    count = await service.sync()
    return {"synced": count}


@router.post("/leetcode/sync")
async def sync_leetcode(service: LeetCodeSyncServiceDep) -> dict[str, int]:
    count = await service.sync()
    return {"synced": count}


@router.post("/codeforces/refresh-metrics")
async def refresh_codeforces_metrics(
    sync_service: CodeforcesSyncServiceDep, platform_service: CsPlatformServiceDep
) -> dict[str, int | bool]:
    platform = await platform_service.get_platform_by_code("codeforces")
    if platform is not None and _already_refreshed_today(platform.metrics_refreshed_at):
        return {"updated": 0, "skipped": True}
    updated = await sync_service.refresh_metrics()
    return {"updated": updated, "skipped": False}


@router.post("/leetcode/refresh-metrics")
async def refresh_leetcode_metrics(
    sync_service: LeetCodeSyncServiceDep, platform_service: CsPlatformServiceDep
) -> dict[str, int | bool]:
    platform = await platform_service.get_platform_by_code("leetcode")
    if platform is not None and _already_refreshed_today(platform.metrics_refreshed_at):
        return {"updated": 0, "skipped": True}
    updated = await sync_service.refresh_metrics()
    return {"updated": updated, "skipped": False}
