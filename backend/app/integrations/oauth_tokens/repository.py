from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.oauth_tokens.tables import OAuthToken


async def get_oauth_token(session: AsyncSession, provider: str) -> OAuthToken | None:
    result = await session.execute(
        select(OAuthToken).where(OAuthToken.provider == provider)
    )
    return result.scalars().first()


async def upsert_oauth_token(session: AsyncSession, provider: str, refresh_token: str) -> None:
    stmt = (
        insert(OAuthToken)
        .values(provider=provider, refresh_token=refresh_token)
        .on_conflict_do_update(
            index_elements=["provider"],
            set_={"refresh_token": refresh_token, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
    await session.commit()


async def delete_oauth_token(session: AsyncSession, provider: str) -> None:
    await session.execute(delete(OAuthToken).where(OAuthToken.provider == provider))
    await session.commit()
