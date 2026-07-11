import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.db.session import get_session
from app.features.watcher.repository import (
    get_alerts,
    get_pending_alerts_with_context,
    resolve_alerts,
)
from app.features.watcher.schemas import AlertRead, AlertResolveRequest, build_alert_read

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watcher/alerts", tags=["watcher"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    status: Literal["pending", "done"] | None = Query(default=None),
    config_id: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return await get_alerts(
        session=session,
        status=status,
        config_id=config_id,
        skip=skip,
        limit=limit,
    )


@router.get("/pending", response_model=list[AlertRead])
async def list_pending_alerts_for_notification(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    alerts = await get_pending_alerts_with_context(session=session)
    return [build_alert_read(alert) for alert in alerts[:limit]]


@router.post("/resolve", response_model=list[AlertRead])
async def resolve_pending_alerts(
    payload: AlertResolveRequest,
    session: AsyncSession = Depends(get_session),
):
    alerts = await resolve_alerts(session=session, alert_ids=payload.alert_ids)
    logger.info("Watcher alerts resolved: ids=%s", payload.alert_ids)
    return [AlertRead.model_validate(alert) for alert in alerts]
