import os

# Must be set before any app module is imported — db/session.py and config.py
# read env vars at import time, and get_settings() is @lru_cache.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/testdb")
os.environ.setdefault("ALFRED_API_TOKEN", "test-api-token")
os.environ.setdefault("NOTION_API_KEY", "test-notion-key")
os.environ.setdefault("NOTION_BASE_URL", "https://api.notion.com/v1")
os.environ.setdefault("NOTION_API_VERSION", "2022-06-28")
os.environ.setdefault("NOTION_TASKS_DATABASE_ID", "test-tasks-db-id")
os.environ.setdefault("NOTION_NOTES_DATABASE_ID", "test-notes-db-id")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

TEST_TOKEN = "test-api-token"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return AUTH_HEADERS.copy()


@pytest.fixture
def mock_session():
    return AsyncMock()
