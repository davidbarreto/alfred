from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import TrackServiceDep
from app.features.language.tracks.schemas import TrackCreate, TrackFilters, TrackRead, TrackUpdate

router = APIRouter(prefix="/language/tracks", tags=["language"], dependencies=[Depends(require_auth)])


@router.post("/", response_model=TrackRead, status_code=status.HTTP_201_CREATED)
async def create_track(request: TrackCreate, service: TrackServiceDep):
    return await service.create_track(request)


@router.get("/", response_model=list[TrackRead])
async def get_tracks(service: TrackServiceDep, filters: TrackFilters = Depends()):
    return await service.get_tracks(filters)


@router.get("/{track_id}", response_model=TrackRead)
async def get_track(track_id: int, service: TrackServiceDep):
    track = await service.get_track(track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    return track


@router.patch("/{track_id}", response_model=TrackRead)
async def update_track(track_id: int, request: TrackUpdate, service: TrackServiceDep):
    track = await service.update_track(track_id, request)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    return track


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_track(track_id: int, service: TrackServiceDep):
    await service.delete_track(track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
