from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_url: str = Field(default="http://api:8000", validation_alias="BACKEND_URL")
    alfred_api_token: str = Field(validation_alias="ALFRED_API_TOKEN")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
