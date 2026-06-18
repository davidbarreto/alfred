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

from fastapi import FastAPI
from typing import AsyncGenerator

from app.api.routes.monitoring.monitors import router as monitors_router
from app.api.routes.monitoring.alerts import router as alerts_router
from app.api.routes.monitoring.executions import router as executions_router
from app.api.routes.integrations.provider_calls import router as provider_calls_router
from app.api.routes.integrations.llm_calls import router as llm_calls_router
from app.api.routes.integrations.google_calendar import router as google_calendar_oauth_router
from app.api.routes.commands import router as commands_router
from app.api.routes.organizer.tasks import router as tasks_router
from app.api.routes.organizer.notes import router as notes_router
from app.api.routes.organizer.calendar_events import router as calendar_events_router
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
from app.api.routes.core.chats import router as core_chats_router
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
app.include_router(monitors_router)
app.include_router(alerts_router)
app.include_router(executions_router)
app.include_router(provider_calls_router)
app.include_router(llm_calls_router)
app.include_router(google_calendar_oauth_router)
app.include_router(commands_router)
app.include_router(tasks_router)
app.include_router(notes_router)
app.include_router(calendar_events_router)
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
app.include_router(core_chats_router)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "database_url": settings.database_url,
    }
