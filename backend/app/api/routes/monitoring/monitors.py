from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import require_auth

from app.features.monitoring.repository import (
    create_monitor,
    delete_monitor,
    get_executions,
    get_monitor,
    get_monitors,
    update_monitor,
)
from app.db.session import get_session
from app.features.monitoring.schemas import (
    ExecutionRead,
    MonitorCreate,
    MonitorRead,
    MonitorUpdate,
)
from app.features.monitoring.service import MonitorService

router = APIRouter(prefix="/monitors", tags=["monitors"], dependencies=[Depends(require_auth)])


@router.get("/", response_model=list[MonitorRead])
async def read_monitors(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    return await get_monitors(session=session, skip=skip, limit=limit)


@router.get("/{monitor_id}", response_model=MonitorRead)
async def read_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)):
    monitor = await get_monitor(session=session, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


@router.post("/", response_model=MonitorRead)
async def create_new_monitor(
    monitor_create: MonitorCreate,
    session: AsyncSession = Depends(get_session),
):
    return await create_monitor(session=session, monitor_create=monitor_create)


@router.delete("/{monitor_id}", response_model=MonitorRead)
async def delete_existing_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)):
    monitor = await delete_monitor(session=session, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


@router.patch("/{monitor_id}", response_model=MonitorRead)
async def patch_monitor(
    monitor_id: int,
    monitor_update: MonitorUpdate,
    session: AsyncSession = Depends(get_session),
):
    monitor = await update_monitor(
        session=session,
        monitor_id=monitor_id,
        monitor_update=monitor_update,
    )
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


@router.post("/run", response_model=list[ExecutionRead])
async def run_active_monitors(session: AsyncSession = Depends(get_session)):
    return await MonitorService.run_due(session=session)


@router.post("/{monitor_id}/run", response_model=ExecutionRead)
async def run_monitor_by_id(monitor_id: int, session: AsyncSession = Depends(get_session)):
    execution = await MonitorService.run_monitor_by_id(session=session, monitor_id=monitor_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return execution


@router.get("/{monitor_id}/executions", response_model=list[ExecutionRead])
async def read_monitor_executions(
    monitor_id: int,
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    monitor = await get_monitor(session=session, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return await get_executions(session=session, monitor_id=monitor_id, limit=limit)
