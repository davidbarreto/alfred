from functools import lru_cache
from typing import Annotated
from fastapi import Depends, HTTPException, status
from app.config import get_settings
from app.integrations.notion.client import NotionClient
from app.integrations.notion.provider import NotionProvider
from app.integrations.google_calendar.client import GoogleCalendarClient
from app.integrations.google_calendar.provider import GoogleCalendarProvider
from app.integrations.frankfurter.client import FrankfurterClient
from app.integrations.frankfurter.provider import FrankfurterProvider
from app.integrations.oauth_tokens.repository import get_oauth_token
from app.features.organizer.tasks.service import TaskService
from app.features.organizer.notes.service import NoteService
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.shopping.service import ShoppingService
from app.features.organizer.shopping_categories.service import ShoppingCategoryService
from app.features.finance.accounts.service import AccountService
from app.features.finance.categories.service import CategoryService
from app.features.finance.currencies.service import CurrencyService
from app.features.finance.exchange_rates.service import ExchangeRateService
from app.features.finance.transactions.service import TransactionService
from app.features.finance.imports.service import ImportService
from app.features.finance.imports.registry import all_parsers
from app.features.finance.installment_plans.service import InstallmentPlanService
from app.features.finance.budgets.service import BudgetTargetService
from app.features.finance.settings.service import FinanceSettingsService
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
from app.features.briefing.morning_summary_service import MorningBriefingSummaryService
from app.features.briefing.morning_formatter_service import MorningBriefingFormatterService
from app.features.briefing.evening_summary_service import EveningDigestSummaryService
from app.features.briefing.evening_formatter_service import EveningDigestFormatterService
from app.features.briefing.history_service import BriefingHistoryService
from app.features.core.reminders.service import ReminderService
from app.integrations.open_meteo.client import OpenMeteoClient
from app.integrations.open_meteo.provider import OpenMeteoProvider
from app.integrations.google_public_holidays.client import GooglePublicHolidayClient
from app.integrations.google_public_holidays.provider import GooglePublicHolidayProvider
from app.features.language.tracks.service import TrackService
from app.features.language.grammar_scope.service import GrammarScopeService
from app.features.language.chunks.service import ChunkService as LanguageChunkService
from app.features.language.chunks.pronunciation_service import PronunciationService
from app.integrations.google_translate_tts.client import GoogleTranslateTtsClient
from app.integrations.ffmpeg.client import FfmpegClient
from app.integrations.file_storage.client import LocalFileStorage
from app.integrations.file_storage.null_client import NullFileStorage
from app.shared.audio import FileStorage
from app.integrations.google.audio_analysis_provider import GoogleAudioAnalysisProvider
from app.integrations.google.transcription_provider import GoogleTranscriptionProvider
from app.integrations.google.conversation_provider import GoogleConversationProvider
from app.integrations.google.tts_provider import GoogleTtsProvider
from app.features.core.transcription.service import TranscriptionService
from app.features.language.chunks.repository import ChunkRepository as LanguageChunkRepository
from app.features.language.tracks.repository import TrackRepository
from app.features.language.sessions.repository import SessionRepository as LanguageSessionRepository
from app.features.language.sessions.service import SessionService as LanguageSessionService
from app.features.language.sessions.shadowing_service import ShadowingService
from app.features.language.production.service import ProductionService
from app.features.language.conversation.repository import ConversationRepository
from app.features.language.conversation.service import ConversationService
from app.features.organizer.contacts.service import ContactService
from app.integrations.google_contacts.client import GoogleContactsClient
from app.integrations.google_contacts.provider import GoogleContactsProvider
from app.integrations.sentence_transformers.provider import SentenceTransformerEmbeddingProvider
from app.integrations.google.llm_provider import GoogleLlmProvider
from app.integrations.null.llm_provider import NullLlmProvider
from app.integrations.null.storage_provider import NullStorageProvider
from app.integrations.null.exchange_rate_provider import NullExchangeRateProvider
from app.integrations.null.weather_provider import NullWeatherProvider
from app.integrations.null.holiday_provider import NullHolidayProvider
from app.integrations.null.pronunciation_provider import NullPronunciationProvider
from app.integrations.null.conversation_provider import NullConversationProvider
from app.integrations.null.audio_analysis_provider import NullAudioAnalysisProvider
from app.integrations.null.transcription_provider import NullTranscriptionProvider
from app.shared.llm import LlmProvider
from app.shared.storage import StorageProvider
from app.shared.exchange_rate import ExchangeRateProvider
from app.shared.weather import WeatherProvider
from app.shared.holiday import HolidayProvider
from app.shared.pronunciation import PronunciationProvider
from app.shared.conversation import ConversationProvider
from app.shared.audio import AudioAnalysisProvider, TranscriptionProvider
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.features.cs.platforms.service import PlatformService
from app.features.cs.platforms.codeforces_sync_service import CodeforcesSyncService
from app.features.cs.platforms.leetcode_sync_service import LeetCodeSyncService
from app.features.cs.problems.service import ProblemService as CsProblemService
from app.features.cs.submissions.service import SubmissionService as CsSubmissionService
from app.features.cs.stats.service import StatsService as CsStatsService
from app.features.cs.study_plans.service import StudyPlanService as CsStudyPlanService
from app.features.cs.recommendations.service import RecommendationService as CsRecommendationService
from app.integrations.codeforces.client import CodeforcesClient
from app.integrations.leetcode.client import LeetCodeClient

@lru_cache
def get_notion_client() -> NotionClient:
    s = get_settings()
    return NotionClient(api_key=s.notion_api_key, base_url=s.notion_base_url, api_version=s.notion_api_version)

@lru_cache
def get_task_provider() -> StorageProvider:
    if get_settings().disable_integrations:
        return NullStorageProvider()
    return NotionProvider(get_notion_client(), get_settings().notion_tasks_database_id, entity_type="task")

@lru_cache
def get_note_provider() -> StorageProvider:
    if get_settings().disable_integrations:
        return NullStorageProvider()
    return NotionProvider(get_notion_client(), get_settings().notion_notes_database_id, content_field="content", entity_type="note")

def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    return TaskService(get_task_provider(), session, EmbeddingService(session, get_embedding_provider()))

def get_note_service(session: AsyncSession = Depends(get_session)) -> NoteService:
    return NoteService(get_note_provider(), session, EmbeddingService(session, get_embedding_provider()))

@lru_cache
def get_null_calendar_provider() -> NullStorageProvider:
    return NullStorageProvider()

@lru_cache
def get_null_contacts_provider() -> NullStorageProvider:
    return NullStorageProvider()

async def get_google_calendar_client(session: AsyncSession = Depends(get_session)) -> GoogleCalendarClient:
    s = get_settings()
    token = await get_oauth_token(session, "google_calendar")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar not authorized. Open GET /integration/google-calendar/oauth/url to start the flow.",
        )
    return GoogleCalendarClient(
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        refresh_token=token.refresh_token,
    )

async def get_calendar_event_service(session: AsyncSession = Depends(get_session)) -> CalendarEventService:
    if get_settings().disable_integrations:
        return CalendarEventService(get_null_calendar_provider(), session)
    try:
        client = await get_google_calendar_client(session)
        provider: StorageProvider | None = GoogleCalendarProvider(
            client, get_settings().google_calendar_id, entity_type="calendar_event"
        )
    except HTTPException:
        provider = None
    return CalendarEventService(provider, session)

def get_shopping_service(session: AsyncSession = Depends(get_session)) -> ShoppingService:
    return ShoppingService(session)

def get_shopping_category_service(session: AsyncSession = Depends(get_session)) -> ShoppingCategoryService:
    return ShoppingCategoryService(session)

def get_account_service(session: AsyncSession = Depends(get_session)) -> AccountService:
    return AccountService(session)

def get_category_service(session: AsyncSession = Depends(get_session)) -> CategoryService:
    return CategoryService(session)

def get_currency_service(session: AsyncSession = Depends(get_session)) -> CurrencyService:
    return CurrencyService(session)

@lru_cache
def get_frankfurter_client() -> FrankfurterClient:
    return FrankfurterClient()

@lru_cache
def get_exchange_rate_provider() -> ExchangeRateProvider:
    if get_settings().disable_integrations:
        return NullExchangeRateProvider()
    return FrankfurterProvider(get_frankfurter_client())

def get_exchange_rate_service(session: AsyncSession = Depends(get_session)) -> ExchangeRateService:
    return ExchangeRateService(session, get_exchange_rate_provider())

def get_transaction_service(session: AsyncSession = Depends(get_session)) -> TransactionService:
    return TransactionService(session, get_exchange_rate_service(session))

def get_budget_target_service(session: AsyncSession = Depends(get_session)) -> BudgetTargetService:
    return BudgetTargetService(session)

def get_finance_settings_service(session: AsyncSession = Depends(get_session)) -> FinanceSettingsService:
    return FinanceSettingsService(session)

def get_recurring_transaction_service(session: AsyncSession = Depends(get_session)) -> RecurringTransactionService:
    return RecurringTransactionService(session, get_exchange_rate_service(session))

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
    if s.disable_integrations:
        return NullLlmProvider()
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return GoogleLlmProvider(api_key=s.gemini_api_key, model_name=s.llm_chat_model, temperature=s.llm_chat_temperature)

@lru_cache
def get_extraction_llm_provider() -> LlmProvider:
    s = get_settings()
    if s.disable_integrations:
        return NullLlmProvider()
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return GoogleLlmProvider(api_key=s.gemini_api_key, model_name=s.llm_extraction_model)

def get_embedding_service(session: AsyncSession = Depends(get_session)) -> EmbeddingService:
    return EmbeddingService(session, get_embedding_provider())

def get_import_service(session: AsyncSession = Depends(get_session)) -> ImportService:
    try:
        llm_provider = get_extraction_llm_provider()
    except RuntimeError:
        llm_provider = None
    return ImportService(
        session=session,
        parsers=all_parsers(),
        embedding_service=EmbeddingService(session, get_embedding_provider()),
        exchange_rate_service=get_exchange_rate_service(session),
        llm_provider=llm_provider,
        file_storage=LocalFileStorage(get_settings().statement_storage_dir),
    )

def get_installment_plan_service(session: AsyncSession = Depends(get_session)) -> InstallmentPlanService:
    return InstallmentPlanService(session)

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
        working_memory_service=WorkingMemoryService(session),
        chunk_service=LanguageChunkService(session),
        production_service=get_production_service(session),
        language_session_service=get_language_session_service(session),
    )

@lru_cache
def get_weather_client() -> OpenMeteoClient:
    return OpenMeteoClient()

@lru_cache
def get_weather_provider() -> WeatherProvider:
    if get_settings().disable_integrations:
        return NullWeatherProvider()
    return OpenMeteoProvider(get_weather_client())

def get_holiday_client() -> GooglePublicHolidayClient | None:
    s = get_settings()
    if not s.gcp_api_key:
        return None
    return GooglePublicHolidayClient(api_key=s.gcp_api_key)

def get_holiday_provider() -> HolidayProvider | None:
    if get_settings().disable_integrations:
        return NullHolidayProvider()
    client = get_holiday_client()
    if client is None:
        return None
    return GooglePublicHolidayProvider(client)

async def get_google_contacts_client(session: AsyncSession = Depends(get_session)) -> GoogleContactsClient | None:
    s = get_settings()
    token = await get_oauth_token(session, "google_contacts")
    if not token:
        return None
    return GoogleContactsClient(
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        refresh_token=token.refresh_token,
    )

async def get_contact_service(session: AsyncSession = Depends(get_session)) -> ContactService | None:
    if get_settings().disable_integrations:
        return ContactService(session=session, client=None, provider=get_null_contacts_provider())
    client = await get_google_contacts_client(session)
    if not client:
        return None
    provider = GoogleContactsProvider(client, entity_type="contact")
    return ContactService(session=session, client=client, provider=provider)

async def get_contacts_crud_service(session: AsyncSession = Depends(get_session)) -> ContactService:
    if get_settings().disable_integrations:
        return ContactService(session=session, client=None, provider=get_null_contacts_provider())
    client = await get_google_contacts_client(session)
    provider = GoogleContactsProvider(client, entity_type="contact") if client else None
    return ContactService(session=session, client=client, provider=provider)

async def get_morning_briefing_summary_service(session: AsyncSession = Depends(get_session)) -> MorningBriefingSummaryService:
    contact_service = await get_contact_service(session)
    return MorningBriefingSummaryService(
        session=session,
        weather_client=get_weather_provider(),
        holiday_client=get_holiday_provider(),
        contact_service=contact_service,
    )

def get_morning_briefing_formatter_service(session: AsyncSession = Depends(get_session)) -> MorningBriefingFormatterService:
    return MorningBriefingFormatterService(llm_provider=get_llm_provider(), session=session)

def get_evening_digest_summary_service(session: AsyncSession = Depends(get_session)) -> EveningDigestSummaryService:
    return EveningDigestSummaryService(session=session)

def get_evening_digest_formatter_service(session: AsyncSession = Depends(get_session)) -> EveningDigestFormatterService:
    return EveningDigestFormatterService(llm_provider=get_llm_provider(), session=session)

def get_briefing_history_service(session: AsyncSession = Depends(get_session)) -> BriefingHistoryService:
    return BriefingHistoryService(session=session)

def get_reminder_service(session: AsyncSession = Depends(get_session)) -> ReminderService:
    return ReminderService(session=session, task_service=get_task_service(session))

def get_track_service(session: AsyncSession = Depends(get_session)) -> TrackService:
    return TrackService(session, chunk_service=get_language_chunk_service(session))

def get_grammar_scope_service(session: AsyncSession = Depends(get_session)) -> GrammarScopeService:
    return GrammarScopeService(session)

def get_language_chunk_service(session: AsyncSession = Depends(get_session)) -> LanguageChunkService:
    try:
        llm_provider = get_llm_provider()
    except RuntimeError:
        llm_provider = None
    return LanguageChunkService(session, llm_provider=llm_provider)

def get_file_storage() -> LocalFileStorage:
    return LocalFileStorage(get_settings().audio_storage_dir)

def get_conversation_audio_storage() -> FileStorage:
    if get_settings().persist_conversation_audio:
        return get_file_storage()
    return NullFileStorage()

def get_pronunciation_service() -> PronunciationService:
    if get_settings().disable_integrations:
        return PronunciationService(NullPronunciationProvider(), FfmpegClient(), get_file_storage())
    return PronunciationService(GoogleTranslateTtsClient(), FfmpegClient(), get_file_storage())

def get_conversation_tts_service() -> PronunciationService:
    s = get_settings()
    if s.disable_integrations:
        return PronunciationService(
            NullPronunciationProvider(), FfmpegClient(), get_conversation_audio_storage(),
            cache_namespace="conversation_tts_cache",
        )
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    provider = GoogleTtsProvider(
        api_key=s.gemini_api_key, model_name=s.llm_conversation_tts_model, voice_name=s.conversation_tts_voice
    )
    return PronunciationService(
        provider, FfmpegClient(), get_conversation_audio_storage(), cache_namespace="conversation_tts_cache"
    )

def get_language_session_service(session: AsyncSession = Depends(get_session)) -> LanguageSessionService:
    return LanguageSessionService(session, WorkingMemoryService(session))

def get_audio_analysis_provider() -> AudioAnalysisProvider:
    s = get_settings()
    if s.disable_integrations:
        return NullAudioAnalysisProvider()
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return GoogleAudioAnalysisProvider(api_key=s.gemini_api_key, model_name=s.llm_pronunciation_model)

def get_conversation_provider() -> ConversationProvider:
    s = get_settings()
    if s.disable_integrations:
        return NullConversationProvider()
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return GoogleConversationProvider(api_key=s.gemini_api_key, model_name=s.llm_conversation_model)

def get_transcription_provider() -> TranscriptionProvider:
    s = get_settings()
    if s.disable_integrations:
        return NullTranscriptionProvider()
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return GoogleTranscriptionProvider(api_key=s.gemini_api_key, model_name=s.llm_transcription_model)

def get_transcription_service(session: AsyncSession = Depends(get_session)) -> TranscriptionService:
    return TranscriptionService(provider=get_transcription_provider(), session=session)

def get_production_service(session: AsyncSession = Depends(get_session)) -> ProductionService:
    return ProductionService(
        session=session,
        llm_provider=get_llm_provider(),
        session_service=get_language_session_service(session),
        chunk_service=LanguageChunkService(session),
        chunk_repo=LanguageChunkRepository(session),
        track_repo=TrackRepository(session),
        session_repo=LanguageSessionRepository(session),
        audio_storage=get_file_storage(),
        audio_converter=FfmpegClient(),
        transcription_service=TranscriptionService(provider=get_transcription_provider(), session=session),
    )

def get_shadowing_service(session: AsyncSession = Depends(get_session)) -> ShadowingService:
    return ShadowingService(
        session=session,
        session_service=get_language_session_service(session),
        audio_storage=get_file_storage(),
        audio_converter=FfmpegClient(),
        analysis_provider=get_audio_analysis_provider(),
    )

def get_cs_platform_service(session: AsyncSession = Depends(get_session)) -> PlatformService:
    return PlatformService(session)

def get_cs_problem_service(session: AsyncSession = Depends(get_session)) -> CsProblemService:
    return CsProblemService(session)

def get_cs_submission_service(session: AsyncSession = Depends(get_session)) -> CsSubmissionService:
    return CsSubmissionService(session)

def get_cs_stats_service(session: AsyncSession = Depends(get_session)) -> CsStatsService:
    return CsStatsService(session)

def get_cs_study_plan_service(session: AsyncSession = Depends(get_session)) -> CsStudyPlanService:
    return CsStudyPlanService(session)

def get_cs_recommendation_service(session: AsyncSession = Depends(get_session)) -> CsRecommendationService:
    return CsRecommendationService(llm_provider=get_extraction_llm_provider(), session=session)

def get_codeforces_sync_service(session: AsyncSession = Depends(get_session)) -> CodeforcesSyncService:
    return CodeforcesSyncService(session, CodeforcesClient())

def get_leetcode_sync_service(session: AsyncSession = Depends(get_session)) -> LeetCodeSyncService:
    s = get_settings()
    if not s.leetcode_session or not s.leetcode_csrf_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LeetCode not configured. Set LEETCODE_SESSION and LEETCODE_CSRF_TOKEN.",
        )
    client = LeetCodeClient(session_cookie=s.leetcode_session, csrf_token=s.leetcode_csrf_token)
    return LeetCodeSyncService(session, client)

def get_conversation_service(session: AsyncSession = Depends(get_session)) -> ConversationService:
    return ConversationService(
        session=session,
        thread_repo=ConversationRepository(session),
        message_service=MessageService(session),
        language_session_service=get_language_session_service(session),
        track_repo=TrackRepository(session),
        chunk_service=get_language_chunk_service(session),
        audio_storage=get_conversation_audio_storage(),
        audio_converter=FfmpegClient(),
        conversation_provider=get_conversation_provider(),
        pronunciation_service=get_conversation_tts_service(),
        llm_provider=get_llm_provider(),
    )

# Dependencies shortcuts
# DB
DbSessionDep = Annotated[AsyncSession, Depends(get_session)]

# Services
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
ShoppingServiceDep = Annotated[ShoppingService, Depends(get_shopping_service)]
ShoppingCategoryServiceDep = Annotated[ShoppingCategoryService, Depends(get_shopping_category_service)]
NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]
CalendarEventServiceDep = Annotated[CalendarEventService, Depends(get_calendar_event_service)]
AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
CurrencyServiceDep = Annotated[CurrencyService, Depends(get_currency_service)]
TransactionServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]
ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]
InstallmentPlanServiceDep = Annotated[InstallmentPlanService, Depends(get_installment_plan_service)]
BudgetTargetServiceDep = Annotated[BudgetTargetService, Depends(get_budget_target_service)]
FinanceSettingsServiceDep = Annotated[FinanceSettingsService, Depends(get_finance_settings_service)]
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
ContactsCRUDServiceDep = Annotated[ContactService, Depends(get_contacts_crud_service)]
MorningBriefingSummaryServiceDep = Annotated[MorningBriefingSummaryService, Depends(get_morning_briefing_summary_service)]
MorningBriefingFormatterServiceDep = Annotated[MorningBriefingFormatterService, Depends(get_morning_briefing_formatter_service)]
EveningDigestSummaryServiceDep = Annotated[EveningDigestSummaryService, Depends(get_evening_digest_summary_service)]
EveningDigestFormatterServiceDep = Annotated[EveningDigestFormatterService, Depends(get_evening_digest_formatter_service)]
BriefingHistoryServiceDep = Annotated[BriefingHistoryService, Depends(get_briefing_history_service)]
ReminderServiceDep = Annotated[ReminderService, Depends(get_reminder_service)]
TrackServiceDep = Annotated[TrackService, Depends(get_track_service)]
GrammarScopeServiceDep = Annotated[GrammarScopeService, Depends(get_grammar_scope_service)]
ChunkServiceDep = Annotated[LanguageChunkService, Depends(get_language_chunk_service)]
PronunciationServiceDep = Annotated[PronunciationService, Depends(get_pronunciation_service)]
LanguageSessionServiceDep = Annotated[LanguageSessionService, Depends(get_language_session_service)]
FileStorageDep = Annotated[LocalFileStorage, Depends(get_file_storage)]
ShadowingServiceDep = Annotated[ShadowingService, Depends(get_shadowing_service)]
ProductionServiceDep = Annotated[ProductionService, Depends(get_production_service)]
ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
TranscriptionServiceDep = Annotated[TranscriptionService, Depends(get_transcription_service)]
CsPlatformServiceDep = Annotated[PlatformService, Depends(get_cs_platform_service)]
CsProblemServiceDep = Annotated[CsProblemService, Depends(get_cs_problem_service)]
CsSubmissionServiceDep = Annotated[CsSubmissionService, Depends(get_cs_submission_service)]
CsStatsServiceDep = Annotated[CsStatsService, Depends(get_cs_stats_service)]
CsStudyPlanServiceDep = Annotated[CsStudyPlanService, Depends(get_cs_study_plan_service)]
CsRecommendationServiceDep = Annotated[CsRecommendationService, Depends(get_cs_recommendation_service)]
CodeforcesSyncServiceDep = Annotated[CodeforcesSyncService, Depends(get_codeforces_sync_service)]
LeetCodeSyncServiceDep = Annotated[LeetCodeSyncService, Depends(get_leetcode_sync_service)]
