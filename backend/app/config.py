from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(validation_alias="DATABASE_URL")
    
    # API auth
    alfred_api_token: str = Field(validation_alias="ALFRED_API_TOKEN")

    # Notion
    notion_api_key: str = Field(validation_alias="NOTION_API_KEY")
    notion_base_url: str = Field(default="https://api.notion.com/v1", validation_alias="NOTION_BASE_URL")
    notion_api_version: str = Field(default="2022-06-28", validation_alias="NOTION_API_VERSION")
    notion_tasks_database_id: str = Field(validation_alias="NOTION_TASKS_DATABASE_ID")
    notion_notes_database_id: str = Field(validation_alias="NOTION_NOTES_DATABASE_ID")

    # Google OAuth (shared client used by Calendar and Contacts)
    google_client_id: str = Field(validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(validation_alias="GOOGLE_CLIENT_SECRET")
    google_calendar_oauth_redirect_uri: str = Field(validation_alias="GOOGLE_CALENDAR_OAUTH_REDIRECT_URI")
    google_calendar_id: str = Field(default="primary", validation_alias="GOOGLE_CALENDAR_ID")
    google_contacts_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/integration/google-contacts/oauth/callback",
        validation_alias="GOOGLE_CONTACTS_OAUTH_REDIRECT_URI",
    )

    # Embeddings
    embedding_model: str = Field(default="all-MiniLM-L6-v2", validation_alias="EMBEDDING_MODEL")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    # LLM (argument extraction via Gemini free tier) — AI Studio key, Generative Language API only
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    # General Google Cloud API key (Calendar API, etc.) — separate from the Gemini key above,
    # which cannot be granted access to other Google APIs
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    llm_chat_model: str = Field(default="gemini-2.0-flash", validation_alias="LLM_CHAT_MODEL")
    llm_chat_temperature: float = Field(default=0.35, validation_alias="LLM_CHAT_TEMPERATURE")
    llm_extraction_model: str = Field(default="gemini-2.5-flash-lite", validation_alias="LLM_EXTRACTION_MODEL")
    llm_pronunciation_model: str = Field(default="gemini-2.5-flash", validation_alias="LLM_PRONUNCIATION_MODEL")
    llm_transcription_model: str = Field(default="gemini-2.5-flash", validation_alias="LLM_TRANSCRIPTION_MODEL")
    intent_threshold: float = Field(default=0.75, validation_alias="INTENT_THRESHOLD")

    # Telegram
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")

    # Local timezone (IANA name) — also mapped to n8n's GENERIC_TIMEZONE in docker-compose
    timezone: str = Field(default="Europe/Lisbon", validation_alias="TIMEZONE")

    # Audio storage — shadowing recordings + pronunciation TTS cache
    audio_storage_dir: str = Field(default="/data/audio", validation_alias="AUDIO_STORAGE_DIR")

    # Statement storage — original bank statement files kept per import batch
    statement_storage_dir: str = Field(default="/data/statements", validation_alias="STATEMENT_STORAGE_DIR")

    # CORS — comma-separated list of allowed origins for browser clients
    # e.g. "http://localhost:8080,https://portal.dbflabs.com"
    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")

    # Reminders — undated-task escalation
    undated_task_escalation_days: int = Field(default=30, validation_alias="UNDATED_TASK_ESCALATION_DAYS")
    undated_task_snooze_days: int = Field(default=7, validation_alias="UNDATED_TASK_SNOOZE_DAYS")

@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore[call-arg]
