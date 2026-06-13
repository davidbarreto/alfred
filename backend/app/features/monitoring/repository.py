from datetime import datetime, timezone
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.monitoring.schemas import ExecutionFilters

from app.features.monitoring.tables import Alert, Execution, Monitor
from app.features.monitoring.schemas import MonitorCreate, MonitorUpdate


async def get_monitor(session: AsyncSession, monitor_id: int) -> Monitor | None:
    result = await session.execute(select(Monitor).where(Monitor.id == monitor_id))
    return result.scalars().first()


async def get_monitors(session: AsyncSession, skip: int = 0, limit: int = 100) -> list[Monitor]:
    result = await session.execute(select(Monitor).offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_active_monitors(session: AsyncSession) -> list[Monitor]:
    result = await session.execute(select(Monitor).where(Monitor.enabled.is_(True)))
    return list(result.scalars().all())


async def create_monitor(session: AsyncSession, monitor_create: MonitorCreate) -> Monitor:
    monitor = Monitor(**monitor_create.model_dump())
    session.add(monitor)
    await session.commit()
    await session.refresh(monitor)
    return monitor


async def update_monitor(
    session: AsyncSession,
    monitor_id: int,
    monitor_update: MonitorUpdate,
) -> Monitor | None:
    monitor = await get_monitor(session, monitor_id)
    if monitor is None:
        return None

    for field, value in monitor_update.model_dump(exclude_unset=True).items():
        setattr(monitor, field, value)

    await session.commit()
    await session.refresh(monitor)
    return monitor


async def delete_monitor(session: AsyncSession, monitor_id: int) -> Monitor | None:
    monitor = await get_monitor(session, monitor_id)
    if monitor is None:
        return None

    await session.execute(delete(Monitor).where(Monitor.id == monitor_id))
    await session.commit()
    return monitor


async def create_execution(
    session: AsyncSession, monitor: Monitor, status: str, result: str | None, error: str | None
) -> Execution:
    snapshot = {
        "name": monitor.name,
        "description": monitor.description,
        "type": monitor.type,
        "url": monitor.url,
        "selector": monitor.selector,
        "json_path": monitor.json_path,
        "target": monitor.target,
        "case_sensitive": monitor.case_sensitive,
        "timeout": monitor.timeout,
        "page_size": monitor.page_size,
        "max_pages": monitor.max_pages,
        "request_delay": monitor.request_delay,
        "wait_selector": monitor.wait_selector,
    }
    execution = Execution(
        config_id=monitor.id,
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


async def _get_latest_alert_for_monitor(
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
    """Create, reopen, or skip an alert for the monitor that triggered this execution.

    Rules:
    - No existing alert → create pending
    - Existing pending → do nothing (already queued)
    - Existing done → reopen as pending, point to current execution
    """
    existing = await _get_latest_alert_for_monitor(session, execution.config_id)

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
