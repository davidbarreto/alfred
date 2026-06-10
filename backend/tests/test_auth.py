import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.api.auth import require_auth


def _make_auth_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    def protected(credentials=Depends(require_auth)):
        return {"status": "ok"}

    return app


@pytest.fixture(scope="module")
def auth_client():
    return TestClient(_make_auth_app())


class TestRequireAuth:
    def test_valid_token_passes(self, auth_client):
        response = auth_client.get(
            "/protected", headers={"Authorization": "Bearer test-api-token"}
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_wrong_token_raises_401(self, auth_client):
        response = auth_client.get(
            "/protected", headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401

    def test_empty_token_raises_403(self, auth_client):
        # HTTPBearer rejects empty credentials before reaching our token comparison
        response = auth_client.get(
            "/protected", headers={"Authorization": "Bearer "}
        )
        assert response.status_code == 403

    def test_missing_authorization_header_raises_403(self, auth_client):
        response = auth_client.get("/protected")
        # HTTPBearer returns 403 when no bearer token is provided
        assert response.status_code == 403

    def test_non_bearer_scheme_raises_403(self, auth_client):
        response = auth_client.get(
            "/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"}
        )
        assert response.status_code == 403
