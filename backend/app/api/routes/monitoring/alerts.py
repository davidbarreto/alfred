from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.db.session import get_session
from app.features.monitoring.repository import get_alerts
from app.features.monitoring.schemas import AlertRead

router = APIRouter(prefix="/monitoring/alerts", tags=["monitoring"], dependencies=[Depends(require_auth)])


@router.get("/", response_model=list[AlertRead])
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
