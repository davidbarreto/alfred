import os

# Must be set before any app module is imported — config.py reads env vars at
# import time via a module-level get_settings() call, and Settings has no
# defaults for these fields.
os.environ.setdefault("ALFRED_API_TOKEN", "test-api-token")
os.environ.setdefault("WEB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

WEB_PASSWORD = os.environ["WEB_PASSWORD"]


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def anon_client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(anon_client):
    anon_client.post("/login", data={"password": WEB_PASSWORD})
    return anon_client


@pytest.fixture
def mock_api(monkeypatch):
    """Patch app.client's HTTP verbs so route tests never hit the network."""
    import app.client as api

    mocks = {name: AsyncMock() for name in ("get", "post", "put", "patch", "delete", "get_bytes", "post_multipart")}
    for name, mock in mocks.items():
        monkeypatch.setattr(api, name, mock)
    return mocks
