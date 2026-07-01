from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.db.session import get_session
from app.integrations.provider_calls.repository import get_sync_log, get_sync_logs
from app.integrations.provider_calls.schemas import SyncLogRead

router = APIRouter(
    prefix="/integration/provider-calls",
    tags=["integrations"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[SyncLogRead])
async def read_provider_calls(
    provider: str | None = Query(default=None),
    operation: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Search in error and provider_entity_id"),
    after: datetime | None = Query(default=None, description="Return calls created after this timestamp"),
    before: datetime | None = Query(default=None, description="Return calls created before this timestamp"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    return await get_sync_logs(
        session,
        provider=provider,
        operation=operation,
        entity_type=entity_type,
        status=status,
        q=q,
        after=after,
        before=before,
        skip=skip,
        limit=limit,
    )


@router.get("/{call_id}", response_model=SyncLogRead)
async def read_provider_call(call_id: int, session: AsyncSession = Depends(get_session)):
    call = await get_sync_log(session, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Provider call not found")
    return call
