from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.embedding_calls.tables import EmbeddingCall


async def create_embedding_call(
    session: AsyncSession,
    *,
    feature: str,
    query_text: str,
    source_types: list[str] | None,
    top_k: int,
    threshold: float,
    results: list[dict[str, Any]],
    result_count: int,
    latency_ms: int | None,
) -> EmbeddingCall:
    call = EmbeddingCall(
        feature=feature,
        query_text=query_text,
        source_types=source_types,
        top_k=top_k,
        threshold=threshold,
        results=results,
        result_count=result_count,
        latency_ms=latency_ms,
    )
    session.add(call)
    await session.commit()
    await session.refresh(call)
    return call


async def get_embedding_calls(
    session: AsyncSession,
    *,
    feature: str | None = None,
    q: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[EmbeddingCall]:
    query = select(EmbeddingCall).order_by(EmbeddingCall.created_at.desc())
    if feature:
        query = query.where(EmbeddingCall.feature == feature)
    if q:
        pattern = f"%{q}%"
        query = query.where(EmbeddingCall.query_text.ilike(pattern))
    if after:
        query = query.where(EmbeddingCall.created_at > after)
    if before:
        query = query.where(EmbeddingCall.created_at < before)
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_distinct_features(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(EmbeddingCall.feature).distinct().order_by(EmbeddingCall.feature)
    )
    return list(result.scalars().all())


async def get_embedding_call(session: AsyncSession, call_id: int) -> EmbeddingCall | None:
    result = await session.execute(select(EmbeddingCall).where(EmbeddingCall.id == call_id))
    return result.scalars().first()
