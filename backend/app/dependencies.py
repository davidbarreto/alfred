from functools import lru_cache
from typing import Annotated
from fastapi import Depends, HTTPException, status
from app.config import get_settings
from app.integrations.notion.client import NotionClient
from app.integrations.notion.provider import NotionProvider
from app.integrations.google_calendar.client import GoogleCalendarClient
from app.integrations.google_calendar.provider import GoogleCalendarProvider
from app.integrations.oauth_tokens.repository import get_oauth_token
from app.features.organizer.tasks.service import TaskService
from app.features.organizer.notes.service import NoteService
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.shopping.service import ShoppingService
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
from app.features.core.memories.extraction_service import MemoryExtractionService
from app.features.core.sessions.summary_service import SessionSummaryService
from app.features.briefing.summary_service import BriefingSummaryService
from app.features.briefing.formatter_service import BriefingFormatterService
from app.features.briefing.weather_client import WeatherClient
from app.features.briefing.holiday_client import GooglePublicHolidayClient
from app.features.organizer.contacts.service import ContactService
from app.integrations.google_contacts.client import GoogleContactsClient
from app.integrations.sentence_transformers.provider import SentenceTransformerEmbeddingProvider
from app.integrations.google.llm_provider import GoogleLlmProvider
from app.shared.llm import LlmProvider
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
    return NotionProvider(get_notion_client(), get_settings().notion_notes_database_id, content_field="content", entity_type="note")

def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    return TaskService(get_task_provider(), session)

def get_note_service(session: AsyncSession = Depends(get_session)) -> NoteService:
    return NoteService(get_note_provider(), session)

async def get_google_calendar_client(session: AsyncSession = Depends(get_session)) -> GoogleCalendarClient:
    s = get_settings()
    token = await get_oauth_token(session, "google_calendar")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar not authorized. Open GET /integration/google-calendar/oauth/url to start the flow.",
        )
    return GoogleCalendarClient(
        client_id=s.google_calendar_client_id,
        client_secret=s.google_calendar_client_secret,
        refresh_token=token.refresh_token,
    )

async def get_calendar_event_service(session: AsyncSession = Depends(get_session)) -> CalendarEventService:
    try:
        client = await get_google_calendar_client(session)
        provider: GoogleCalendarProvider | None = GoogleCalendarProvider(
            client, get_settings().google_calendar_id, entity_type="calendar_event"
        )
    except HTTPException:
        provider = None
    return CalendarEventService(provider, session)

def get_shopping_service(session: AsyncSession = Depends(get_session)) -> ShoppingService:
    return ShoppingService(session)

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

@lru_cache
def get_llm_provider() -> LlmProvider:
    s = get_settings()
    if not s.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set")
    return GoogleLlmProvider(api_key=s.google_api_key, model_name=s.llm_chat_model, temperature=s.llm_chat_temperature)

@lru_cache
def get_extraction_llm_provider() -> LlmProvider:
    s = get_settings()
    if not s.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set")
    return GoogleLlmProvider(api_key=s.google_api_key, model_name=s.llm_extraction_model)

def get_embedding_service(session: AsyncSession = Depends(get_session)) -> EmbeddingService:
    return EmbeddingService(session, get_embedding_provider())

@lru_cache
def get_memory_extraction_service() -> MemoryExtractionService:
    return MemoryExtractionService(
        llm_provider=get_extraction_llm_provider(),
        embedding_provider=get_embedding_provider(),
    )

@lru_cache
def get_session_summary_service() -> SessionSummaryService:
    return SessionSummaryService(llm_provider=get_extraction_llm_provider())

def get_chat_service(session: AsyncSession = Depends(get_session)) -> ChatService:
    return ChatService(
        session=session,
        llm_provider=get_llm_provider(),
        embedding_service=EmbeddingService(session, get_embedding_provider()),
        message_service=MessageService(session),
        memory_extraction_service=get_memory_extraction_service(),
        session_summary_service=get_session_summary_service(),
    )

@lru_cache
def get_weather_client() -> WeatherClient:
    return WeatherClient()

def get_holiday_client() -> GooglePublicHolidayClient:
    s = get_settings()
    if not s.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set")
    return GooglePublicHolidayClient(api_key=s.google_api_key)

async def get_google_contacts_client(session: AsyncSession = Depends(get_session)) -> GoogleContactsClient | None:
    s = get_settings()
    token = await get_oauth_token(session, "google_contacts")
    if not token:
        return None
    return GoogleContactsClient(
        client_id=s.google_calendar_client_id,
        client_secret=s.google_calendar_client_secret,
        refresh_token=token.refresh_token,
    )

async def get_contact_service(session: AsyncSession = Depends(get_session)) -> ContactService | None:
    client = await get_google_contacts_client(session)
    if not client:
        return None
    return ContactService(client=client, session=session)

async def get_briefing_summary_service(session: AsyncSession = Depends(get_session)) -> BriefingSummaryService:
    contact_service = await get_contact_service(session)
    return BriefingSummaryService(
        session=session,
        weather_client=get_weather_client(),
        holiday_client=get_holiday_client(),
        contact_service=contact_service,
    )

def get_briefing_formatter_service(session: AsyncSession = Depends(get_session)) -> BriefingFormatterService:
    return BriefingFormatterService(llm_provider=get_llm_provider(), session=session)

# Dependencies shortcuts
# DB
DbSessionDep = Annotated[AsyncSession, Depends(get_session)]

# Services
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
ShoppingServiceDep = Annotated[ShoppingService, Depends(get_shopping_service)]
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
SessionSummaryServiceDep = Annotated[SessionSummaryService, Depends(get_session_summary_service)]
LlmProviderDep = Annotated[LlmProvider, Depends(get_llm_provider)]
ExtractionLlmProviderDep = Annotated[LlmProvider, Depends(get_extraction_llm_provider)]
ContactServiceDep = Annotated[ContactService | None, Depends(get_contact_service)]
BriefingSummaryServiceDep = Annotated[BriefingSummaryService, Depends(get_briefing_summary_service)]
BriefingFormatterServiceDep = Annotated[BriefingFormatterService, Depends(get_briefing_formatter_service)]
