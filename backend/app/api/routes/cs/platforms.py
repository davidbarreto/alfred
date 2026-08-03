from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CodeforcesSyncServiceDep, CsPlatformServiceDep, LeetCodeSyncServiceDep
from app.features.cs.platforms.schemas import PlatformCreate, PlatformFilters, PlatformRead, PlatformUpdate

router = APIRouter(prefix="/cs/platforms", tags=["cs"], dependencies=[Depends(require_auth)])


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
