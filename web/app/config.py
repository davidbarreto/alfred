from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_url: str = Field(default="http://api:8000", validation_alias="BACKEND_URL")
    alfred_api_token: str = Field(validation_alias="ALFRED_API_TOKEN")
    # Exposed to the chat page JS so the browser can open the SSE stream
    # directly to the backend. Same value as ALFRED_API_TOKEN — acceptable
    # for a personal, single-user portal running on a private server.
    web_port: int = Field(default=8080, validation_alias="WEB_PORT")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
