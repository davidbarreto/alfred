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

@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore[call-arg]
