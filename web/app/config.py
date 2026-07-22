from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_url: str = Field(default="http://api:8000", validation_alias="BACKEND_URL")
    # Browser-accessible backend URL — used only in the chat page JS for the SSE call.
    # Differs from BACKEND_URL when running in Docker (internal vs host-visible address).
    public_backend_url: str = Field(default="http://localhost:8000", validation_alias="PUBLIC_BACKEND_URL")
    alfred_api_token: str = Field(validation_alias="ALFRED_API_TOKEN")
    web_port: int = Field(default=8080, validation_alias="WEB_PORT")
    web_password: str = Field(validation_alias="WEB_PASSWORD")
    session_secret_key: str = Field(validation_alias="SESSION_SECRET_KEY")
    # Local timezone (IANA name) — must match the backend's TIMEZONE, since it's the
    # zone the backend normalizes all stored calendar/task datetimes to.
    timezone: str = Field(default="Europe/Lisbon", validation_alias="TIMEZONE")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
