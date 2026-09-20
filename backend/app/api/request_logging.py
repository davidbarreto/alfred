import asyncio
import logging
import time
from typing import Awaitable, Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.db.session import async_session
from app.features.core.api_requests.service import ApiRequestService

logger = logging.getLogger(__name__)

CLIENT_HEADER = b"x-alfred-client"
UNMATCHED_ROUTE = "<unmatched>"
_RECORD_TIMEOUT_SECONDS = 2.0
# /core/api-requests is what the Insights page reads: logging it would make merely
# viewing the charts inflate them.
_EXCLUDED_PATHS = frozenset({"/health"})
_EXCLUDED_PREFIXES = ("/core/api-requests",)

Recorder = Callable[..., Awaitable[None]]


async def _record_to_db(**fields) -> None:
    async with async_session() as session:
        await ApiRequestService(session).record(**fields)


def _is_excluded(scope: Scope) -> bool:
    path = scope["path"]
    return (
        scope["method"] == "OPTIONS"
        or path in _EXCLUDED_PATHS
        or path.startswith(_EXCLUDED_PREFIXES)
    )


def _client_header(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == CLIENT_HEADER:
            return value.decode("latin-1")
    return None


class ApiRequestLoggingMiddleware:
    """Records one row per HTTP request (caller, route template, status, latency).

    Written as pure ASGI rather than BaseHTTPMiddleware so streaming responses (the chat
    SSE stream) pass through untouched. The row is written after the response has been
    sent, and a logging failure never affects the request.
    """

    def __init__(self, app: ASGIApp, recorder: Recorder | None = None) -> None:
        self.app = app
        self._recorder = recorder

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _is_excluded(scope):
            await self.app(scope, receive, send)
            return

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            await self._record(scope, status_code, started)

    async def _record(self, scope: Scope, status_code: int, started: float) -> None:
        route = scope.get("route")
        # Resolved per call (not bound in __init__) so tests can swap the DB writer out.
        recorder = self._recorder or _record_to_db
        try:
            await asyncio.wait_for(
                recorder(
                    client=_client_header(scope),
                    method=scope["method"],
                    route=getattr(route, "path", UNMATCHED_ROUTE),
                    status_code=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                ),
                timeout=_RECORD_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("API request logging failed: %s: %s", type(exc).__name__, exc)
