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
    google_calendar_refresh_token: str = Field(validation_alias="GOOGLE_CALENDAR_REFRESH_TOKEN")
    google_calendar_id: str = Field(default="primary", validation_alias="GOOGLE_CALENDAR_ID")

@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore[call-arg]
