from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(validation_alias="DATABASE_URL")


@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore[call-arg]


settings = get_settings()
