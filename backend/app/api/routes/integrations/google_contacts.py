from __future__ import annotations

import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.config import get_settings
from app.db.session import get_session
from app.dependencies import ContactServiceDep
from app.integrations.oauth_tokens.repository import get_oauth_token, upsert_oauth_token

router = APIRouter(
    prefix="/integration/google-contacts",
    tags=["integrations"],
)

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPES = ["https://www.googleapis.com/auth/contacts.readonly"]


@router.get("/status", dependencies=[Depends(require_auth)])
async def get_status(session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    token = await get_oauth_token(session, "google_contacts")
    return {"authorized": token is not None}


@router.get("/oauth/url", dependencies=[Depends(require_auth)])
async def get_oauth_url() -> dict[str, str]:
    s = get_settings()
    params = {
        "client_id": s.google_calendar_client_id,
        "redirect_uri": s.google_contacts_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return {"url": f"{_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"}


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    s = get_settings()
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": s.google_calendar_client_id,
                "client_secret": s.google_calendar_client_secret,
                "redirect_uri": s.google_contacts_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if resp.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Token exchange failed: {resp.text}",
        )

    data = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google did not return a refresh token. Re-open the auth URL (it forces re-consent).",
        )

    await upsert_oauth_token(session, "google_contacts", refresh_token)
    return {"status": "ok", "message": "Google Contacts authorized successfully."}


@router.post("/sync", dependencies=[Depends(require_auth)])
async def sync_contacts(service: ContactServiceDep) -> dict[str, int]:
    count = await service.sync()
    return {"synced": count}
