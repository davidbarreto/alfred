from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.monitoring.tables import Monitor, MonitorLog
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


async def create_monitor_log(
    session: AsyncSession, monitor: Monitor, result: dict
) -> MonitorLog:
    log = MonitorLog(
        monitor_id=monitor.id,
        monitor_name=monitor.name,
        monitor_description=monitor.description,
        monitor_type=monitor.type,
        url=monitor.url,
        selector=monitor.selector,
        json_path=monitor.json_path,
        target=monitor.target,
        case_sensitive=monitor.case_sensitive,
        timeout=monitor.timeout,
        page_size=monitor.page_size,
        max_pages=monitor.max_pages,
        request_delay=monitor.request_delay,
        wait_selector=monitor.wait_selector,
        found=result.get("found", False),
        elements_checked=result.get("elements_checked", 0),
        error=result.get("error"),
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_monitor_logs(
    session: AsyncSession,
    monitor_id: int,
    limit: int = 20,
) -> list[MonitorLog]:
    result = await session.execute(
        select(MonitorLog)
        .where(MonitorLog.monitor_id == monitor_id)
        .order_by(MonitorLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
