import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routes import auth, briefing, contacts, dashboard, tasks, shopping, calendar, notes, finance, chat, insights

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Alfred Portal", docs_url=None, redoc_url=None)

_PUBLIC_PATHS = {"/login", "/logout"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS or request.url.path.startswith("/static"):
            return await call_next(request)
        if not request.session.get("authenticated"):
            return RedirectResponse(f"/login?next={request.url.path}", status_code=302)
        return await call_next(request)


s = get_settings()
# add_middleware is LIFO: last added = outermost = runs first.
# SessionMiddleware must be outermost so request.session is ready for AuthMiddleware.
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=s.session_secret_key, https_only=False)

_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(tasks.router)
app.include_router(shopping.router)
app.include_router(calendar.router)
app.include_router(contacts.router)
app.include_router(notes.router)
app.include_router(finance.router)
app.include_router(insights.router)
app.include_router(briefing.router)
app.include_router(chat.router)
