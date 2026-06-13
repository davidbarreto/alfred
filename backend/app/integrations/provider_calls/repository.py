from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.provider_calls.tables import IntegrationSyncLog


async def create_sync_log(
    session: AsyncSession,
    *,
    provider: str,
    operation: str,
    entity_type: str,
    provider_entity_id: str | None,
    status: str,
    request_payload: dict | None,
    response_payload: dict | None,
    error: str | None,
) -> IntegrationSyncLog:
    log = IntegrationSyncLog(
        provider=provider,
        operation=operation,
        entity_type=entity_type,
        provider_entity_id=provider_entity_id,
        status=status,
        request_payload=request_payload,
        response_payload=response_payload,
        error=error,
    )
    session.add(log)
    return log


async def get_sync_logs(
    session: AsyncSession,
    *,
    provider: str | None = None,
    operation: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[IntegrationSyncLog]:
    query = select(IntegrationSyncLog).order_by(IntegrationSyncLog.created_at.desc())
    if provider:
        query = query.where(IntegrationSyncLog.provider == provider)
    if operation:
        query = query.where(IntegrationSyncLog.operation == operation)
    if entity_type:
        query = query.where(IntegrationSyncLog.entity_type == entity_type)
    if status:
        query = query.where(IntegrationSyncLog.status == status)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                IntegrationSyncLog.error.ilike(pattern),
                IntegrationSyncLog.provider_entity_id.ilike(pattern),
            )
        )
    if after:
        query = query.where(IntegrationSyncLog.created_at > after)
    if before:
        query = query.where(IntegrationSyncLog.created_at < before)
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_sync_log(session: AsyncSession, log_id: int) -> IntegrationSyncLog | None:
    result = await session.execute(
        select(IntegrationSyncLog).where(IntegrationSyncLog.id == log_id)
    )
    return result.scalars().first()
