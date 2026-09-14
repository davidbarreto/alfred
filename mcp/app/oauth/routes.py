from __future__ import annotations

import html
import logging
import secrets
import time
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from app.config import get_settings
from app.oauth import templates
from app.oauth.pkce import verify_pkce
from app.oauth.store import OAuthStore

logger = logging.getLogger(__name__)

store = OAuthStore(get_settings().oauth_db_path)

_DEFAULT_SCOPE = "alfred"
# Open DCR endpoints are the norm for MCP servers, but this one is internet-facing —
# cap total registrations so a scripted spammer can't grow the SQLite file unbounded.
_MAX_REGISTERED_CLIENTS = 200
_REQUIRED_AUTHORIZE_PARAMS = ["response_type", "client_id", "redirect_uri", "code_challenge", "code_challenge_method"]


def _base_url() -> str:
    return get_settings().mcp_public_url.rstrip("/")


async def well_known_authorization_server(request: Request) -> JSONResponse:
    base = _base_url()
    return JSONResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
            "registration_endpoint": f"{base}/register",
            "revocation_endpoint": f"{base}/revoke",
            "scopes_supported": [_DEFAULT_SCOPE],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        }
    )


async def well_known_protected_resource(request: Request) -> JSONResponse:
    base = _base_url()
    return JSONResponse(
        {
            "resource": f"{base}/mcp",
            "authorization_servers": [base],
        }
    )


async def register_client(request: Request) -> JSONResponse:
    """Dynamic Client Registration (RFC 7591). Left open to unauthenticated callers,
    same as every DCR-capable MCP server — the actual access grant happens later at
    /authorize, gated behind the Alfred password. Worst case of an open /register is
    junk client rows, not data access."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_client_metadata", "error_description": "Body must be JSON"}, status_code=400)

    redirect_uris = body.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris or not all(isinstance(u, str) for u in redirect_uris):
        return JSONResponse(
            {"error": "invalid_redirect_uri", "error_description": "redirect_uris must be a non-empty array of strings"},
            status_code=400,
        )

    if await store.count_clients() >= _MAX_REGISTERED_CLIENTS:
        logger.warning("Rejected client registration: registration cap reached")
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "Registration limit reached"},
            status_code=429,
        )

    client_name = body.get("client_name")
    auth_method = body.get("token_endpoint_auth_method", "none")
    if auth_method not in ("none", "client_secret_post"):
        auth_method = "none"

    client, client_secret = await store.create_client(redirect_uris, client_name, auth_method)
    response = {
        "client_id": client.client_id,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": client.redirect_uris,
        "client_name": client.client_name,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
    }
    if client_secret:
        response["client_secret"] = client_secret
    return JSONResponse(response, status_code=201)


def _hidden_fields(params: dict[str, str]) -> str:
    return "\n".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in params.items()
        if v is not None
    )


def _authorize_params(source: dict) -> dict[str, str]:
    return {
        "response_type": source.get("response_type", ""),
        "client_id": source.get("client_id", ""),
        "redirect_uri": source.get("redirect_uri", ""),
        "code_challenge": source.get("code_challenge", ""),
        "code_challenge_method": source.get("code_challenge_method", ""),
        "state": source.get("state", ""),
        "scope": source.get("scope", _DEFAULT_SCOPE),
    }


async def _validate_authorize_request(params: dict[str, str]) -> tuple[str | None, object]:
    """Returns (error_message, client) — error_message is None on success.

    Only once redirect_uri is confirmed registered for this client do later
    errors get sent back to the client via redirect; unknown client / bad
    redirect_uri are shown locally to avoid becoming an open redirect.
    """
    if any(not params.get(k) for k in _REQUIRED_AUTHORIZE_PARAMS):
        return "Missing required OAuth parameter(s).", None
    if params["response_type"] != "code":
        return "Only response_type=code is supported.", None
    client = await store.get_client(params["client_id"])
    if client is None:
        return "Unknown client_id. This app may need to reconnect to register again.", None
    if params["redirect_uri"] not in client.redirect_uris:
        return "redirect_uri does not match the one registered for this client.", None
    if params["code_challenge_method"] != "S256":
        return None, client  # handled as a redirected error later (invalid_request)
    return None, client


async def authorize_get(request: Request) -> HTMLResponse:
    params = _authorize_params(request.query_params)
    error, client = await _validate_authorize_request(params)
    if error:
        return HTMLResponse(templates.error_page(error), status_code=400)
    if params["code_challenge_method"] != "S256":
        return _redirect_with_error(params["redirect_uri"], params["state"], "invalid_request", "PKCE S256 is required")

    hidden = _hidden_fields(params)
    settings = get_settings()
    session = request.session
    authenticated_at = session.get("authenticated_at")
    if not authenticated_at or (time.time() - authenticated_at) > settings.login_remember_seconds:
        return HTMLResponse(templates.login_page(hidden))

    consent_token = secrets.token_urlsafe(16)
    session["consent_token"] = consent_token
    return HTMLResponse(templates.consent_page(client.client_name, hidden + _hidden_fields({"consent_token": consent_token})))


async def authorize_login(request: Request) -> HTMLResponse | RedirectResponse:
    form = await request.form()
    params = _authorize_params(form)
    error, client = await _validate_authorize_request(params)
    if error:
        return HTMLResponse(templates.error_page(error), status_code=400)

    if form.get("password") != get_settings().oauth_login_password:
        logger.warning("MCP login failed: client_id=%s", params["client_id"])
        return HTMLResponse(templates.login_page(_hidden_fields(params), error="Incorrect password."), status_code=401)

    request.session["authenticated_at"] = time.time()
    query = urlencode({k: v for k, v in params.items() if v})
    return RedirectResponse(f"/authorize?{query}", status_code=303)


async def authorize_consent(request: Request) -> RedirectResponse | HTMLResponse:
    form = await request.form()
    params = _authorize_params(form)
    error, client = await _validate_authorize_request(params)
    if error:
        return HTMLResponse(templates.error_page(error), status_code=400)

    settings = get_settings()
    authenticated_at = request.session.get("authenticated_at")
    if not authenticated_at or (time.time() - authenticated_at) > settings.login_remember_seconds:
        return HTMLResponse(templates.login_page(_hidden_fields(params)))

    submitted_token = form.get("consent_token")
    if not submitted_token or submitted_token != request.session.get("consent_token"):
        return HTMLResponse(templates.error_page("Consent request expired or invalid. Please retry."), status_code=400)
    request.session.pop("consent_token", None)

    if form.get("decision") != "approve":
        return _redirect_with_error(params["redirect_uri"], params["state"], "access_denied", "User denied access")

    code = await store.create_auth_code(
        client_id=params["client_id"],
        redirect_uri=params["redirect_uri"],
        code_challenge=params["code_challenge"],
        code_challenge_method=params["code_challenge_method"],
        scope=params["scope"],
        ttl_seconds=settings.auth_code_ttl_seconds,
    )
    logger.info("OAuth authorization granted: client_id=%s", params["client_id"])
    query = {"code": code}
    if params["state"]:
        query["state"] = params["state"]
    return RedirectResponse(f"{params['redirect_uri']}?{urlencode(query)}", status_code=303)


def _redirect_with_error(redirect_uri: str, state: str, error: str, description: str) -> RedirectResponse:
    query = {"error": error, "error_description": description}
    if state:
        query["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(query)}", status_code=303)


async def token_endpoint(request: Request) -> JSONResponse:
    form = await request.form()
    grant_type = form.get("grant_type")
    settings = get_settings()

    if grant_type == "authorization_code":
        code = form.get("code")
        client_id = form.get("client_id")
        redirect_uri = form.get("redirect_uri")
        code_verifier = form.get("code_verifier")
        if not all([code, client_id, redirect_uri, code_verifier]):
            return JSONResponse({"error": "invalid_request"}, status_code=400)

        if not await store.verify_client_secret(client_id, form.get("client_secret")):
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        record = await store.consume_auth_code(code)
        if record is None:
            return JSONResponse({"error": "invalid_grant", "error_description": "Code expired, already used, or unknown"}, status_code=400)
        if record["client_id"] != client_id or record["redirect_uri"] != redirect_uri:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if not verify_pkce(code_verifier, record["code_challenge"], record["code_challenge_method"]):
            logger.warning("PKCE verification failed: client_id=%s", client_id)
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)

        pair = await store.issue_token_pair(
            client_id, record["scope"], settings.access_token_ttl_seconds, settings.refresh_token_ttl_seconds
        )
        return JSONResponse(_token_response(pair))

    if grant_type == "refresh_token":
        refresh_token = form.get("refresh_token")
        client_id = form.get("client_id")
        if not refresh_token or not client_id:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        if not await store.verify_client_secret(client_id, form.get("client_secret")):
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        pair = await store.rotate_refresh_token(
            refresh_token, settings.access_token_ttl_seconds, settings.refresh_token_ttl_seconds
        )
        if pair is None:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        return JSONResponse(_token_response(pair))

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


def _token_response(pair) -> dict:
    return {
        "access_token": pair.access_token,
        "token_type": "Bearer",
        "expires_in": pair.expires_in,
        "refresh_token": pair.refresh_token,
        "scope": pair.scope,
    }


async def revoke_endpoint(request: Request) -> JSONResponse:
    form = await request.form()
    token = form.get("token")
    if token:
        await store.revoke_by_pair_of(token)
    # RFC 7009: always return 200, even for unknown tokens.
    return JSONResponse({}, status_code=200)


routes = [
    Route("/.well-known/oauth-authorization-server", well_known_authorization_server, methods=["GET"]),
    Route("/.well-known/oauth-protected-resource", well_known_protected_resource, methods=["GET"]),
    Route("/register", register_client, methods=["POST"]),
    Route("/authorize", authorize_get, methods=["GET"]),
    Route("/authorize/login", authorize_login, methods=["POST"]),
    Route("/authorize/consent", authorize_consent, methods=["POST"]),
    Route("/token", token_endpoint, methods=["POST"]),
    Route("/revoke", revoke_endpoint, methods=["POST"]),
]
