import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.api_requests.repository import ApiRequestRepository
from app.features.core.api_requests.schemas import ApiUsageSummary, ClientUsage, RouteUsage

logger = logging.getLogger(__name__)

UNKNOWN_CLIENT = "unknown"
_MAX_CLIENT_LENGTH = 50
_TOP_ROUTES_LIMIT = 10


def _normalise_client(raw: str | None) -> str:
    client = (raw or "").strip().lower()[:_MAX_CLIENT_LENGTH]
    return client or UNKNOWN_CLIENT


class ApiRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ApiRequestRepository(session)

    async def record(
        self, client: str | None, method: str, route: str, status_code: int, duration_ms: int
    ) -> None:
        normalised = _normalise_client(client)
        await self._repo.create(
            client=normalised,
            method=method,
            route=route,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        logger.debug("API request recorded: client=%s method=%s route=%s status=%d", normalised, method, route, status_code)

    async def get_summary(self, days: int) -> ApiUsageSummary:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        client_rows = await self._repo.usage_by_client(since=since)
        route_rows = await self._repo.usage_by_route(since=since, limit=_TOP_ROUTES_LIMIT)
        by_client = [
            ClientUsage(
                client=row.client,
                requests=row.requests,
                errors=row.errors,
                avg_latency_ms=float(row.avg_latency_ms or 0),
            )
            for row in client_rows
        ]
        top_routes = [
            RouteUsage(
                client=row.client, method=row.method, route=row.route, requests=row.requests, errors=row.errors
            )
            for row in route_rows
        ]
        logger.debug("API usage summary: days=%d clients=%d routes=%d", days, len(by_client), len(top_routes))
        return ApiUsageSummary(
            days=days,
            total=sum(c.requests for c in by_client),
            by_client=by_client,
            top_routes=top_routes,
        )
