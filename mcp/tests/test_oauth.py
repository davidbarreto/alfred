import base64
import hashlib
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from app.config import get_settings
from app.oauth.routes import store as oauth_store
from app.server import app


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


@pytest.fixture(autouse=True)
async def _fresh_oauth_db():
    db_path = Path(get_settings().oauth_db_path)
    db_path.unlink(missing_ok=True)
    await oauth_store.init()
    yield
    db_path.unlink(missing_ok=True)


@pytest.fixture
def client():
    # Not entered as a context manager on purpose: that would run the app's
    # lifespan, which fetches the command catalog from the Alfred backend —
    # unavailable in this unit-test environment and irrelevant to the OAuth
    # flow under test here (the oauth store is initialized directly above).
    return TestClient(app)


def _register_client(client: TestClient, redirect_uri: str = "https://client.example/callback") -> dict:
    resp = client.post("/register", json={"redirect_uris": [redirect_uri], "client_name": "Test Client"})
    assert resp.status_code == 201
    return resp.json()


class TestDynamicClientRegistration:
    def test_register_returns_client_id_and_no_secret_for_public_client(self, client):
        body = _register_client(client)
        assert body["client_id"]
        assert "client_secret" not in body
        assert body["redirect_uris"] == ["https://client.example/callback"]

    def test_register_confidential_client_gets_secret(self, client):
        resp = client.post(
            "/register",
            json={
                "redirect_uris": ["https://client.example/callback"],
                "token_endpoint_auth_method": "client_secret_post",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["client_secret"]

    def test_register_without_redirect_uris_rejected(self, client):
        resp = client.post("/register", json={"client_name": "Bad Client"})
        assert resp.status_code == 400

    def test_register_capped_at_max_clients(self, client, monkeypatch):
        from app.oauth import routes as routes_module

        monkeypatch.setattr(routes_module, "_MAX_REGISTERED_CLIENTS", 1)
        _register_client(client, redirect_uri="https://client1.example/callback")
        resp = client.post("/register", json={"redirect_uris": ["https://client2.example/callback"]})
        assert resp.status_code == 429

    def test_metadata_endpoints_advertise_registration_and_pkce(self, client):
        resp = client.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        body = resp.json()
        assert body["registration_endpoint"].endswith("/register")
        assert body["code_challenge_methods_supported"] == ["S256"]

        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.json()["resource"].endswith("/mcp")


class TestAuthorizationCodeFlow:
    def _authorize_params(self, client_id: str, challenge: str, redirect_uri: str) -> dict:
        return {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
        }

    def test_full_flow_issues_access_and_refresh_token(self, client):
        registered = _register_client(client)
        verifier, challenge = _pkce_pair()
        params = self._authorize_params(registered["client_id"], challenge, registered["redirect_uris"][0])

        resp = client.get("/authorize", params=params)
        assert "Sign in" in resp.text

        login_resp = client.post("/authorize/login", data={**params, "password": "test-password"}, follow_redirects=False)
        assert login_resp.status_code == 303

        consent_get = client.get("/authorize", params=params)
        assert "Allow" in consent_get.text
        # crude extraction of the consent_token hidden field
        token_marker = 'name="consent_token" value="'
        start = consent_get.text.index(token_marker) + len(token_marker)
        consent_token = consent_get.text[start:consent_get.text.index('"', start)]

        approve_resp = client.post(
            "/authorize/consent",
            data={**params, "consent_token": consent_token, "decision": "approve"},
            follow_redirects=False,
        )
        assert approve_resp.status_code == 303
        redirect_qs = parse_qs(urlparse(approve_resp.headers["location"]).query)
        assert redirect_qs["state"] == ["xyz"]
        code = redirect_qs["code"][0]

        token_resp = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": registered["client_id"],
                "redirect_uri": registered["redirect_uris"][0],
                "code_verifier": verifier,
            },
        )
        assert token_resp.status_code == 200
        tokens = token_resp.json()
        assert tokens["token_type"] == "Bearer"
        assert tokens["access_token"]
        assert tokens["refresh_token"]

        # Auth code is single-use.
        replay_resp = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": registered["client_id"],
                "redirect_uri": registered["redirect_uris"][0],
                "code_verifier": verifier,
            },
        )
        assert replay_resp.status_code == 400

        refresh_resp = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": registered["client_id"],
            },
        )
        assert refresh_resp.status_code == 200
        assert refresh_resp.json()["access_token"] != tokens["access_token"]

        # Old refresh token was rotated out.
        reuse_resp = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": registered["client_id"],
            },
        )
        assert reuse_resp.status_code == 400

    def test_wrong_password_rejected(self, client):
        registered = _register_client(client)
        _, challenge = _pkce_pair()
        params = self._authorize_params(registered["client_id"], challenge, registered["redirect_uris"][0])
        resp = client.post("/authorize/login", data={**params, "password": "wrong"})
        assert resp.status_code == 401
        assert "Incorrect password" in resp.text

    def test_token_exchange_with_wrong_pkce_verifier_rejected(self, client):
        registered = _register_client(client)
        _, challenge = _pkce_pair()
        redirect_uri = registered["redirect_uris"][0]
        params = self._authorize_params(registered["client_id"], challenge, redirect_uri)
        client.post("/authorize/login", data={**params, "password": "test-password"}, follow_redirects=False)
        consent_get = client.get("/authorize", params=params)
        token_marker = 'name="consent_token" value="'
        start = consent_get.text.index(token_marker) + len(token_marker)
        consent_token = consent_get.text[start:consent_get.text.index('"', start)]
        approve_resp = client.post(
            "/authorize/consent",
            data={**params, "consent_token": consent_token, "decision": "approve"},
            follow_redirects=False,
        )
        code = parse_qs(urlparse(approve_resp.headers["location"]).query)["code"][0]

        token_resp = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": registered["client_id"],
                "redirect_uri": redirect_uri,
                "code_verifier": "wrong-verifier",
            },
        )
        assert token_resp.status_code == 400

    def test_unregistered_redirect_uri_rejected(self, client):
        registered = _register_client(client)
        _, challenge = _pkce_pair()
        params = self._authorize_params(registered["client_id"], challenge, "https://evil.example/callback")
        resp = client.get("/authorize", params=params)
        assert resp.status_code == 400
        assert "does not match" in resp.text

    def test_plain_pkce_method_rejected(self, client):
        registered = _register_client(client)
        params = self._authorize_params(registered["client_id"], "somechallenge", registered["redirect_uris"][0])
        params["code_challenge_method"] = "plain"
        resp = client.get("/authorize", params=params, follow_redirects=False)
        assert resp.status_code == 303
        redirect_qs = parse_qs(urlparse(resp.headers["location"]).query)
        assert redirect_qs["error"] == ["invalid_request"]


class TestProtectedResource:
    def test_mcp_without_token_returns_401_with_resource_metadata(self, client):
        resp = client.post("/mcp", json={})
        assert resp.status_code == 401
        assert "resource_metadata" in resp.headers["www-authenticate"]

    def test_mcp_with_invalid_token_returns_401(self, client):
        resp = client.post("/mcp", json={}, headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == 401

    def test_bare_mcp_path_does_not_redirect(self, client):
        # Regression: Starlette's Mount("/mcp", ...) 307-redirects a bare POST /mcp
        # to /mcp/ by default. MCP clients request the bare path and don't reliably
        # resend the Authorization header across that redirect, turning every call
        # into a silent 401 despite a valid token. redirect_slashes=False on the
        # app's router must keep this a direct (non-redirected) request.
        resp = client.post("/mcp", json={}, headers={"Authorization": "Bearer fake"}, follow_redirects=False)
        assert resp.status_code != 307
