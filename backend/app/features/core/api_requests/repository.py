from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.api_requests.tables import ApiRequest

_ERRORS = func.coalesce(func.sum(case((ApiRequest.status_code >= 400, 1), else_=0)), 0)


class ApiRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, client: str, method: str, route: str, status_code: int, duration_ms: int
    ) -> ApiRequest:
        row = ApiRequest(
            client=client,
            method=method,
            route=route,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        self._session.add(row)
        await self._session.commit()
        return row

    async def usage_by_client(self, since: datetime) -> Sequence[Any]:
        result = await self._session.execute(
            select(
                ApiRequest.client,
                func.count().label("requests"),
                _ERRORS.cast(Integer).label("errors"),
                func.avg(ApiRequest.duration_ms).label("avg_latency_ms"),
            )
            .where(ApiRequest.created_at >= since)
            .group_by(ApiRequest.client)
            .order_by(func.count().desc(), ApiRequest.client)
        )
        return result.all()

    async def usage_by_route(self, since: datetime, limit: int) -> Sequence[Any]:
        result = await self._session.execute(
            select(
                ApiRequest.client,
                ApiRequest.method,
                ApiRequest.route,
                func.count().label("requests"),
                _ERRORS.cast(Integer).label("errors"),
            )
            .where(ApiRequest.created_at >= since)
            .group_by(ApiRequest.client, ApiRequest.method, ApiRequest.route)
            .order_by(func.count().desc(), ApiRequest.route)
            .limit(limit)
        )
        return result.all()
