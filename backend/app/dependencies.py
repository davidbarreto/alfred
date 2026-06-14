from functools import lru_cache
from typing import Annotated
from fastapi import Depends
from app.config import get_settings
from app.integrations.notion.client import NotionClient
from app.integrations.notion.provider import NotionProvider
from app.integrations.google_calendar.client import GoogleCalendarClient
from app.integrations.google_calendar.provider import GoogleCalendarProvider
from app.features.organizer.tasks.service import TaskService
from app.features.organizer.notes.service import NoteService
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.finance.accounts.service import AccountService
from app.features.finance.categories.service import CategoryService
from app.features.finance.transactions.service import TransactionService
from app.features.finance.budgets.service import BudgetService
from app.features.finance.recurring_transactions.service import RecurringTransactionService
from app.features.core.sessions.service import SessionService
from app.features.core.messages.service import MessageService
from app.features.core.command_executions.service import CommandExecutionService
from app.features.core.memories.service import MemoryService
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.chats.service import ChatService
from app.integrations.sentence_transformers.provider import SentenceTransformerEmbeddingProvider
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session

@lru_cache
def get_notion_client() -> NotionClient:
    s = get_settings()
    return NotionClient(api_key=s.notion_api_key, base_url=s.notion_base_url, api_version=s.notion_api_version)

@lru_cache
def get_task_provider() -> NotionProvider:
    return NotionProvider(get_notion_client(), get_settings().notion_tasks_database_id, entity_type="task")

@lru_cache
def get_note_provider() -> NotionProvider:
    return NotionProvider(get_notion_client(), get_settings().notion_notes_database_id, content_field="description", entity_type="note")

def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    return TaskService(get_task_provider(), session)

def get_note_service(session: AsyncSession = Depends(get_session)) -> NoteService:
    return NoteService(get_note_provider(), session)

@lru_cache
def get_google_calendar_client() -> GoogleCalendarClient:
    s = get_settings()
    return GoogleCalendarClient(
        client_id=s.google_calendar_client_id,
        client_secret=s.google_calendar_client_secret,
        refresh_token=s.google_calendar_refresh_token,
    )

@lru_cache
def get_calendar_event_provider() -> GoogleCalendarProvider:
    return GoogleCalendarProvider(get_google_calendar_client(), get_settings().google_calendar_id, entity_type="calendar_event")

def get_calendar_event_service(session: AsyncSession = Depends(get_session)) -> CalendarEventService:
    return CalendarEventService(get_calendar_event_provider(), session)

def get_account_service(session: AsyncSession = Depends(get_session)) -> AccountService:
    return AccountService(session)

def get_category_service(session: AsyncSession = Depends(get_session)) -> CategoryService:
    return CategoryService(session)

def get_transaction_service(session: AsyncSession = Depends(get_session)) -> TransactionService:
    return TransactionService(session)

def get_budget_service(session: AsyncSession = Depends(get_session)) -> BudgetService:
    return BudgetService(session)

def get_recurring_transaction_service(session: AsyncSession = Depends(get_session)) -> RecurringTransactionService:
    return RecurringTransactionService(session)

def get_session_service(session: AsyncSession = Depends(get_session)) -> SessionService:
    return SessionService(session)

def get_message_service(session: AsyncSession = Depends(get_session)) -> MessageService:
    return MessageService(session)

def get_command_execution_service(session: AsyncSession = Depends(get_session)) -> CommandExecutionService:
    return CommandExecutionService(session)

def get_memory_service(session: AsyncSession = Depends(get_session)) -> MemoryService:
    return MemoryService(session)

def get_working_memory_service(session: AsyncSession = Depends(get_session)) -> WorkingMemoryService:
    return WorkingMemoryService(session)

@lru_cache
def get_embedding_provider() -> SentenceTransformerEmbeddingProvider:
    return SentenceTransformerEmbeddingProvider(get_settings().embedding_model)

def get_embedding_service(session: AsyncSession = Depends(get_session)) -> EmbeddingService:
    return EmbeddingService(session, get_embedding_provider())

def get_chat_service(session: AsyncSession = Depends(get_session)) -> ChatService:
    return ChatService(
        embedding_service=EmbeddingService(session, get_embedding_provider()),
        message_service=MessageService(session),
    )

# Dependencies shortcuts
# DB
DbSessionDep = Annotated[AsyncSession, Depends(get_session)]

# Services
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]
CalendarEventServiceDep = Annotated[CalendarEventService, Depends(get_calendar_event_service)]
AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
TransactionServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]
BudgetServiceDep = Annotated[BudgetService, Depends(get_budget_service)]
RecurringTransactionServiceDep = Annotated[RecurringTransactionService, Depends(get_recurring_transaction_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]
CommandExecutionServiceDep = Annotated[CommandExecutionService, Depends(get_command_execution_service)]
MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]
WorkingMemoryServiceDep = Annotated[WorkingMemoryService, Depends(get_working_memory_service)]
EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]