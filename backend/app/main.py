import logging
import os
from contextlib import asynccontextmanager

# Configure logging level from environment variable `LOG_LEVEL` (default: INFO)
level_name = os.getenv("LOG_LEVEL", "INFO").upper()
try:
    numeric_level = int(level_name)
except ValueError:
    numeric_level = getattr(logging, level_name, logging.INFO)

logging.basicConfig(level=numeric_level, force=True)

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import AsyncGenerator

from app.api.routes.watcher.watchers import router as watchers_router
from app.api.routes.watcher.alerts import router as alerts_router
from app.api.routes.watcher.executions import router as executions_router
from app.api.routes.integrations.provider_calls import router as provider_calls_router
from app.api.routes.integrations.llm_calls import router as llm_calls_router
from app.api.routes.integrations.google_calendar import router as google_calendar_oauth_router
from app.api.routes.integrations.google_contacts import router as google_contacts_router
from app.api.routes.integrations.telegram import router as telegram_router
from app.api.routes.commands import router as commands_router
from app.api.routes.organizer.tasks import router as tasks_router
from app.api.routes.organizer.notes import router as notes_router
from app.api.routes.organizer.calendar_events import router as calendar_events_router
from app.api.routes.organizer.contacts import router as contacts_router
from app.api.routes.organizer.shopping import shopping_router, wishlist_router, recurrence_router
from app.api.routes.finance.accounts import router as finance_accounts_router
from app.api.routes.finance.categories import router as finance_categories_router
from app.api.routes.finance.transactions import router as finance_transactions_router
from app.api.routes.finance.budgets import router as finance_budgets_router
from app.api.routes.finance.recurring_transactions import router as finance_recurring_router
from app.api.routes.core.sessions import router as core_sessions_router
from app.api.routes.core.messages import router as core_messages_router
from app.api.routes.core.command_executions import router as core_command_executions_router
from app.api.routes.core.memories import router as core_memories_router
from app.api.routes.core.working_memory import router as core_working_memory_router
from app.api.routes.core.embeddings import router as core_embeddings_router
from app.api.routes.core.transcription import router as core_transcription_router
from app.api.routes.core.chats import router as core_chats_router, stream_router as core_chats_stream_router
from app.api.routes.core.reminders import router as core_reminders_router
from app.api.routes.briefing import router as briefing_router
from app.api.routes.language.tracks import router as language_tracks_router
from app.api.routes.language.grammar_scope import router as language_grammar_scope_router
from app.api.routes.language.chunks import router as language_chunks_router
from app.api.routes.language.sessions import router as language_sessions_router
from app.api.routes.language.production import router as language_production_router
from app.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    if not root_logger.handlers:
        logging.basicConfig(level=numeric_level, force=True)
    for handler in root_logger.handlers:
        handler.setLevel(numeric_level)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).setLevel(numeric_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("Startup logging configured: LOG_LEVEL=%s, root_level=%s", level_name, logging.getLogger().getEffectiveLevel())
    app.state.settings = settings
    yield


app = FastAPI(title="Alfred Backend", version="0.1.0", lifespan=lifespan)

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(watchers_router)
app.include_router(alerts_router)
app.include_router(executions_router)
app.include_router(provider_calls_router)
app.include_router(llm_calls_router)
app.include_router(google_calendar_oauth_router)
app.include_router(google_contacts_router)
app.include_router(telegram_router)
app.include_router(commands_router)
app.include_router(tasks_router)
app.include_router(notes_router)
app.include_router(calendar_events_router)
app.include_router(contacts_router)
app.include_router(shopping_router)
app.include_router(wishlist_router)
app.include_router(recurrence_router)
app.include_router(finance_accounts_router)
app.include_router(finance_categories_router)
app.include_router(finance_transactions_router)
app.include_router(finance_budgets_router)
app.include_router(finance_recurring_router)
app.include_router(core_sessions_router)
app.include_router(core_messages_router)
app.include_router(core_command_executions_router)
app.include_router(core_memories_router)
app.include_router(core_working_memory_router)
app.include_router(core_embeddings_router)
app.include_router(core_transcription_router)
app.include_router(core_chats_router)
app.include_router(core_chats_stream_router)
app.include_router(core_reminders_router)
app.include_router(briefing_router)
app.include_router(language_tracks_router)
app.include_router(language_grammar_scope_router)
app.include_router(language_chunks_router)
app.include_router(language_sessions_router)
app.include_router(language_production_router)

@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "Request validation error %s %s body=%s errors=%s",
        request.method,
        request.url.path,
        await request.body(),
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "database_url": settings.database_url,
    }
