from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    client_secret_hash TEXT,
    client_name TEXT,
    redirect_uris TEXT NOT NULL,
    token_endpoint_auth_method TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_codes (
    code_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    code_challenge TEXT NOT NULL,
    code_challenge_method TEXT NOT NULL,
    scope TEXT NOT NULL,
    expires_at REAL NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    token_type TEXT NOT NULL,
    client_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    expires_at REAL,
    revoked INTEGER NOT NULL DEFAULT 0,
    pair_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tokens_pair ON tokens(pair_id);
"""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


@dataclass
class Client:
    client_id: str
    client_secret_hash: str | None
    client_name: str | None
    redirect_uris: list[str]
    token_endpoint_auth_method: str


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str


class OAuthStore:
    """SQLite-backed storage for OAuth clients, authorization codes, and tokens.

    Single-user, low-traffic server — a file-backed SQLite DB is enough and
    keeps this concern out of the shared Postgres instance the Alfred backend
    owns. Secrets/tokens are stored as SHA-256 hashes, never in plaintext.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    async def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        logger.info("OAuth store initialized: path=%s", self._db_path)

    async def create_client(
        self,
        redirect_uris: list[str],
        client_name: str | None,
        token_endpoint_auth_method: str,
    ) -> tuple[Client, str | None]:
        client_id = secrets.token_urlsafe(16)
        client_secret = None
        client_secret_hash = None
        if token_endpoint_auth_method != "none":
            client_secret = secrets.token_urlsafe(32)
            client_secret_hash = _hash(client_secret)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO clients (client_id, client_secret_hash, client_name, redirect_uris, "
                "token_endpoint_auth_method, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    client_id,
                    client_secret_hash,
                    client_name,
                    json.dumps(redirect_uris),
                    token_endpoint_auth_method,
                    time.time(),
                ),
            )
            await db.commit()
        logger.info("OAuth client registered: client_id=%s name=%r", client_id, client_name)
        return (
            Client(client_id, client_secret_hash, client_name, redirect_uris, token_endpoint_auth_method),
            client_secret,
        )

    async def count_clients(self) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM clients")
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_client(self, client_id: str) -> Client | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM clients WHERE client_id = ?", (client_id,))
            row = await cursor.fetchone()
        if row is None:
            return None
        return Client(
            client_id=row["client_id"],
            client_secret_hash=row["client_secret_hash"],
            client_name=row["client_name"],
            redirect_uris=json.loads(row["redirect_uris"]),
            token_endpoint_auth_method=row["token_endpoint_auth_method"],
        )

    async def verify_client_secret(self, client_id: str, client_secret: str | None) -> bool:
        client = await self.get_client(client_id)
        if client is None:
            return False
        if client.token_endpoint_auth_method == "none":
            return True
        if not client_secret:
            return False
        return client.client_secret_hash == _hash(client_secret)

    async def create_auth_code(
        self,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        scope: str,
        ttl_seconds: int,
    ) -> str:
        code = _new_token("code")
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO auth_codes (code_hash, client_id, redirect_uri, code_challenge, "
                "code_challenge_method, scope, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    _hash(code),
                    client_id,
                    redirect_uri,
                    code_challenge,
                    code_challenge_method,
                    scope,
                    time.time() + ttl_seconds,
                ),
            )
            await db.commit()
        return code

    async def consume_auth_code(self, code: str) -> dict[str, Any] | None:
        code_hash = _hash(code)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM auth_codes WHERE code_hash = ?", (code_hash,))
            row = await cursor.fetchone()
            if row is None:
                return None
            record = dict(row)
            # Single-use: delete immediately regardless of validity below, so a
            # replayed/expired code can never be consumed twice.
            await db.execute("DELETE FROM auth_codes WHERE code_hash = ?", (code_hash,))
            await db.commit()
        if record["consumed"] or record["expires_at"] < time.time():
            logger.warning("Rejected auth code: client_id=%s reason=expired_or_consumed", record["client_id"])
            return None
        return record

    async def issue_token_pair(self, client_id: str, scope: str, access_ttl: int, refresh_ttl: int) -> TokenPair:
        access_token = _new_token("at")
        refresh_token = _new_token("rt")
        pair_id = secrets.token_urlsafe(8)
        now = time.time()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO tokens (token_hash, token_type, client_id, scope, expires_at, pair_id) "
                "VALUES (?, 'access', ?, ?, ?, ?)",
                (_hash(access_token), client_id, scope, now + access_ttl, pair_id),
            )
            await db.execute(
                "INSERT INTO tokens (token_hash, token_type, client_id, scope, expires_at, pair_id) "
                "VALUES (?, 'refresh', ?, ?, ?, ?)",
                (_hash(refresh_token), client_id, scope, now + refresh_ttl, pair_id),
            )
            await db.commit()
        logger.info("OAuth token pair issued: client_id=%s", client_id)
        return TokenPair(access_token, refresh_token, access_ttl, scope)

    async def get_valid_access_token(self, token: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tokens WHERE token_hash = ? AND token_type = 'access'",
                (_hash(token),),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        if row["revoked"] or (row["expires_at"] and row["expires_at"] < time.time()):
            return None
        return dict(row)

    async def rotate_refresh_token(self, refresh_token: str, access_ttl: int, refresh_ttl: int) -> TokenPair | None:
        token_hash = _hash(refresh_token)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tokens WHERE token_hash = ? AND token_type = 'refresh'",
                (token_hash,),
            )
            row = await cursor.fetchone()
            if row is None or row["revoked"] or row["expires_at"] < time.time():
                return None
            # Rotate: revoke the whole pair (access + refresh) the old refresh
            # token belonged to before issuing a fresh pair.
            await db.execute("UPDATE tokens SET revoked = 1 WHERE pair_id = ?", (row["pair_id"],))
            await db.commit()
            client_id, scope = row["client_id"], row["scope"]
        return await self.issue_token_pair(client_id, scope, access_ttl, refresh_ttl)

    async def revoke_by_pair_of(self, token: str) -> None:
        token_hash = _hash(token)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT pair_id FROM tokens WHERE token_hash = ?", (token_hash,))
            row = await cursor.fetchone()
            if row is None:
                return
            await db.execute("UPDATE tokens SET revoked = 1 WHERE pair_id = ?", (row["pair_id"],))
            await db.commit()
