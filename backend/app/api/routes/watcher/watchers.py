from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import require_auth

from app.features.watcher.repository import (
    create_watcher,
    delete_watcher,
    get_executions,
    get_watcher,
    get_watchers,
    update_watcher,
)
from app.db.session import get_session
from app.features.watcher.schemas import (
    ExecutionRead,
    WatcherCreate,
    WatcherRead,
    WatcherUpdate,
)
from app.features.watcher.service import WatcherService

router = APIRouter(prefix="/watcher/configs", tags=["watcher"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[WatcherRead])
async def read_watchers(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    return await get_watchers(session=session, skip=skip, limit=limit)


@router.get("/{watcher_id}", response_model=WatcherRead)
async def read_watcher(watcher_id: int, session: AsyncSession = Depends(get_session)):
    watcher = await get_watcher(session=session, watcher_id=watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher


@router.post("", response_model=WatcherRead)
async def create_new_watcher(
    watcher_create: WatcherCreate,
    session: AsyncSession = Depends(get_session),
):
    return await create_watcher(session=session, watcher_create=watcher_create)


@router.delete("/{watcher_id}", response_model=WatcherRead)
async def delete_existing_watcher(watcher_id: int, session: AsyncSession = Depends(get_session)):
    watcher = await delete_watcher(session=session, watcher_id=watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher


@router.patch("/{watcher_id}", response_model=WatcherRead)
async def patch_watcher(
    watcher_id: int,
    watcher_update: WatcherUpdate,
    session: AsyncSession = Depends(get_session),
):
    watcher = await update_watcher(
        session=session,
        watcher_id=watcher_id,
        watcher_update=watcher_update,
    )
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher


@router.post("/run", response_model=list[ExecutionRead])
async def run_active_watchers(session: AsyncSession = Depends(get_session)):
    return await WatcherService.run_due(session=session)


@router.post("/{watcher_id}/run", response_model=ExecutionRead)
async def run_watcher_by_id(watcher_id: int, session: AsyncSession = Depends(get_session)):
    execution = await WatcherService.run_watcher_by_id(session=session, watcher_id=watcher_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return execution


@router.get("/{watcher_id}/executions", response_model=list[ExecutionRead])
async def read_watcher_executions(
    watcher_id: int,
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    watcher = await get_watcher(session=session, watcher_id=watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return await get_executions(session=session, config_id=watcher_id, limit=limit)
