from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_url: str = Field(default="http://api:8000", validation_alias="BACKEND_URL")
    alfred_api_token: str = Field(validation_alias="ALFRED_API_TOKEN")

    # Public URL this server is reachable at (behind nginx), e.g. "https://mcp.dbflabs.com".
    # Used as the OAuth issuer and to build absolute endpoint URLs in the
    # .well-known metadata documents — required for remote clients (Claude
    # Desktop/web) to discover and complete the OAuth flow correctly.
    mcp_public_url: str = Field(validation_alias="MCP_PUBLIC_URL")

    # Password gate on the /authorize login page. A client (Claude Code, Desktop,
    # claude.ai) opens a browser to this page once per client registration; the
    # single Alfred user authenticates with this password to approve access.
    oauth_login_password: str = Field(validation_alias="MCP_LOGIN_PASSWORD")

    # Signs the browser session cookie used to remember the login step between
    # the /authorize GET and POST. Independent of the web portal's own secret.
    oauth_session_secret: str = Field(validation_alias="MCP_SESSION_SECRET_KEY")

    oauth_db_path: str = Field(default="/data/oauth.db", validation_alias="MCP_OAUTH_DB_PATH")

    access_token_ttl_seconds: int = Field(default=3600, validation_alias="MCP_ACCESS_TOKEN_TTL")
    refresh_token_ttl_seconds: int = Field(default=60 * 60 * 24 * 180, validation_alias="MCP_REFRESH_TOKEN_TTL")
    auth_code_ttl_seconds: int = Field(default=60, validation_alias="MCP_AUTH_CODE_TTL")
    # How long a successful /authorize login is remembered in the browser session,
    # so re-connecting the same browser doesn't re-prompt for the password.
    login_remember_seconds: int = Field(default=60 * 60 * 24 * 30, validation_alias="MCP_LOGIN_REMEMBER_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
