from datetime import datetime, timezone
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.watcher.schemas import ExecutionFilters

from app.features.watcher.tables import Alert, Execution, Watcher
from app.features.watcher.schemas import WatcherCreate, WatcherUpdate


async def get_watcher(session: AsyncSession, watcher_id: int) -> Watcher | None:
    result = await session.execute(select(Watcher).where(Watcher.id == watcher_id))
    return result.scalars().first()


async def get_watchers(session: AsyncSession, skip: int = 0, limit: int = 100) -> list[Watcher]:
    result = await session.execute(select(Watcher).offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_active_watchers(session: AsyncSession) -> list[Watcher]:
    result = await session.execute(select(Watcher).where(Watcher.enabled.is_(True)))
    return list(result.scalars().all())


async def create_watcher(session: AsyncSession, watcher_create: WatcherCreate) -> Watcher:
    watcher = Watcher(**watcher_create.model_dump())
    session.add(watcher)
    await session.commit()
    await session.refresh(watcher)
    return watcher


async def update_watcher(
    session: AsyncSession,
    watcher_id: int,
    watcher_update: WatcherUpdate,
) -> Watcher | None:
    watcher = await get_watcher(session, watcher_id)
    if watcher is None:
        return None

    for field, value in watcher_update.model_dump(exclude_unset=True).items():
        setattr(watcher, field, value)

    await session.commit()
    await session.refresh(watcher)
    return watcher


async def delete_watcher(session: AsyncSession, watcher_id: int) -> Watcher | None:
    watcher = await get_watcher(session, watcher_id)
    if watcher is None:
        return None

    await session.execute(delete(Watcher).where(Watcher.id == watcher_id))
    await session.commit()
    return watcher


async def create_execution(
    session: AsyncSession, watcher: Watcher, status: str, result: str | None, error: str | None
) -> Execution:
    snapshot = {
        "name": watcher.name,
        "description": watcher.description,
        "type": watcher.type,
        "url": watcher.url,
        "selector": watcher.selector,
        "json_path": watcher.json_path,
        "target": watcher.target,
        "case_sensitive": watcher.case_sensitive,
        "timeout": watcher.timeout,
        "page_size": watcher.page_size,
        "max_pages": watcher.max_pages,
        "request_delay": watcher.request_delay,
        "wait_selector": watcher.wait_selector,
    }
    execution = Execution(
        config_id=watcher.id,
        status=status,
        result=result,
        error=error,
        config_snapshot=snapshot,
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    return execution


async def get_executions(
    session: AsyncSession,
    config_id: int,
    limit: int = 20,
) -> list[Execution]:
    result = await session.execute(
        select(Execution)
        .where(Execution.config_id == config_id)
        .order_by(Execution.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_all_executions(
    session: AsyncSession,
    filters: ExecutionFilters,
) -> list[Execution]:
    query = select(Execution)
    if filters.config_id is not None:
        query = query.where(Execution.config_id == filters.config_id)
    if filters.status is not None:
        query = query.where(Execution.status == filters.status)
    if filters.before_date is not None:
        query = query.where(Execution.created_at < filters.before_date)
    if filters.after_date is not None:
        query = query.where(Execution.created_at > filters.after_date)
    if filters.result is not None:
        query = query.where(Execution.result.ilike(f"%{filters.result}%"))
    query = query.order_by(Execution.created_at.desc()).offset(filters.skip).limit(filters.limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_alerts(
    session: AsyncSession,
    status: str | None = None,
    config_id: int | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[Alert]:
    query = select(Alert).join(Execution, Alert.execution_id == Execution.id)
    if status is not None:
        query = query.where(Alert.status == status)
    if config_id is not None:
        query = query.where(Execution.config_id == config_id)
    query = query.order_by(Alert.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def _get_latest_alert_for_watcher(
    session: AsyncSession, config_id: int
) -> Alert | None:
    result = await session.execute(
        select(Alert)
        .join(Execution, Alert.execution_id == Execution.id)
        .where(Execution.config_id == config_id)
        .order_by(Alert.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def upsert_alert(session: AsyncSession, execution: Execution) -> Alert | None:
    """Create, reopen, or skip an alert for the watcher that triggered this execution.

    Rules:
    - No existing alert → create pending
    - Existing pending → do nothing (already queued)
    - Existing done → reopen as pending, point to current execution
    """
    existing = await _get_latest_alert_for_watcher(session, execution.config_id)

    if existing is None:
        alert = Alert(execution_id=execution.id, status="pending")
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert

    if existing.status == "pending":
        return existing

    # status == "done" → reopen
    existing.status = "pending"
    existing.execution_id = execution.id
    existing.resolved_at = None
    await session.commit()
    await session.refresh(existing)
    return existing
