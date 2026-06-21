import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import dashboard, tasks, shopping, calendar, notes, finance, chat

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Alfred Portal", docs_url=None, redoc_url=None)

_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

app.include_router(dashboard.router)
app.include_router(tasks.router)
app.include_router(shopping.router)
app.include_router(calendar.router)
app.include_router(notes.router)
app.include_router(finance.router)
app.include_router(chat.router)
