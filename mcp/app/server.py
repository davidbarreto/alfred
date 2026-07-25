import logging
from contextlib import asynccontextmanager

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from app.backend_client import execute_command, get_catalog
from app.catalog import Catalog, build_tools, resolve_call

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


@asynccontextmanager
async def lifespan(app: Starlette):
    global _catalog, _tools
    # Fetched once at startup, not per-request — restart the container to
    # pick up COMMAND_DEFINITIONS changes made on the backend. If the
    # backend isn't reachable yet (e.g. cold `docker compose up`), this
    # raises and Docker's restart policy retries the container.
    _catalog = await get_catalog()
    _tools = build_tools(_catalog)
    logger.info("Loaded %d tool(s) from Alfred command catalog", len(_tools))
    async with session_manager.run():
        yield


app = Starlette(routes=[Mount("/mcp", app=session_manager.handle_request)], lifespan=lifespan)
