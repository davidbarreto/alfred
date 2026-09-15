import logging
from contextlib import asynccontextmanager

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount

from app.backend_client import execute_command, get_catalog
from app.catalog import Catalog, build_tools, resolve_call
from app.config import get_settings
from app.oauth.routes import routes as oauth_routes
from app.oauth.routes import store as oauth_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp_server = Server("alfred")

_catalog: Catalog = {}
_tools: list[types.Tool] = []


@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return _tools


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> dict:
    cmd_type, action, args = resolve_call(_catalog, name, arguments)
    logger.info("Tool call: %s action=%s", name, action)
    result = await execute_command(cmd_type, action, args)
    return {"result": result}


session_manager = StreamableHTTPSessionManager(
    app=mcp_server,
    # Single-user, no client-side session state worth tracking; every call
    # is a self-contained request against the Alfred backend.
    stateless=True,
    json_response=True,
)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Gates /mcp behind an OAuth access token (RFC 6750 Bearer).

    Everything else (the OAuth endpoints themselves, .well-known metadata) is
    left open — only the MCP tool surface carries Alfred data.
    """

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None
        record = await oauth_store.get_valid_access_token(token) if token else None
        if record is None:
            base = get_settings().mcp_public_url.rstrip("/")
            resource_metadata_url = f"{base}/.well-known/oauth-protected-resource"
            return JSONResponse(
                {"error": "invalid_token"},
                status_code=401,
                headers={"WWW-Authenticate": f'Bearer realm="alfred", resource_metadata="{resource_metadata_url}"'},
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: Starlette):
    global _catalog, _tools
    await oauth_store.init()
    # Fetched once at startup, not per-request — restart the container to
    # pick up COMMAND_DEFINITIONS changes made on the backend. If the
    # backend isn't reachable yet (e.g. cold `docker compose up`), this
    # raises and Docker's restart policy retries the container.
    _catalog = await get_catalog()
    _tools = build_tools(_catalog)
    logger.info("Loaded %d tool(s) from Alfred command catalog", len(_tools))
    async with session_manager.run():
        yield


settings = get_settings()

app = Starlette(
    routes=[*oauth_routes, Mount("/mcp", app=session_manager.handle_request)],
    lifespan=lifespan,
    middleware=[
        # Starlette's `middleware=[...]` list is applied outermost-first, unlike
        # add_middleware()'s LIFO order. SessionMiddleware must be outermost so
        # request.session is populated before the /authorize route handlers run.
        Middleware(SessionMiddleware, secret_key=settings.oauth_session_secret, https_only=False, session_cookie="mcp_session"),
        Middleware(BearerAuthMiddleware),
    ],
)

# Without this, a bare POST /mcp (no trailing slash — what every MCP client
# actually requests) gets a 307 to /mcp/ from Starlette's Mount matching.
# Clients don't reliably resend the Authorization header across that
# redirect, so every call silently 401s despite a valid token.
app.router.redirect_slashes = False
