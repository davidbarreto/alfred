from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(..., env="DATABASE_URL")
    ollama_url: str = Field("http://localhost:11434", env="OLLAMA_URL")
    openai_api_key: str | None = Field(None, env="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(None, env="ANTHROPIC_API_KEY")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
