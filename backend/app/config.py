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

    # Google Calendar
    google_calendar_client_id: str = Field(validation_alias="GOOGLE_CALENDAR_CLIENT_ID")
    google_calendar_client_secret: str = Field(validation_alias="GOOGLE_CALENDAR_CLIENT_SECRET")
    google_calendar_oauth_redirect_uri: str = Field(validation_alias="GOOGLE_CALENDAR_OAUTH_REDIRECT_URI")
    google_calendar_id: str = Field(default="primary", validation_alias="GOOGLE_CALENDAR_ID")

    # Embeddings
    embedding_model: str = Field(default="all-MiniLM-L6-v2", validation_alias="EMBEDDING_MODEL")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    # LLM (argument extraction via Gemini free tier)
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    llm_chat_model: str = Field(default="gemini-2.0-flash", validation_alias="LLM_CHAT_MODEL")
    llm_chat_temperature: float = Field(default=0.35, validation_alias="LLM_CHAT_TEMPERATURE")
    llm_extraction_model: str = Field(default="gemini-2.5-flash-lite", validation_alias="LLM_EXTRACTION_MODEL")
    intent_threshold: float = Field(default=0.75, validation_alias="INTENT_THRESHOLD")

    # CORS — comma-separated list of allowed origins for browser clients
    # e.g. "http://localhost:8080,https://portal.dbflabs.com"
    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")

@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore[call-arg]
