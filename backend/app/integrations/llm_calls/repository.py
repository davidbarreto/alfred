from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm_calls.tables import LlmCall


async def create_llm_call(
    session: AsyncSession,
    *,
    provider: str,
    model: str,
    feature: str,
    prompt: list,
    response: str,
    tokens_input: int | None,
    tokens_output: int | None,
    latency_ms: int | None,
) -> LlmCall:
    call = LlmCall(
        provider=provider,
        model=model,
        feature=feature,
        prompt=prompt,
        response=response,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        latency_ms=latency_ms,
    )
    session.add(call)
    return call


async def get_llm_calls(
    session: AsyncSession,
    *,
    provider: str | None = None,
    model: str | None = None,
    feature: str | None = None,
    q: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[LlmCall]:
    query = select(LlmCall).order_by(LlmCall.created_at.desc())
    if provider:
        query = query.where(LlmCall.provider == provider)
    if model:
        query = query.where(LlmCall.model == model)
    if feature:
        query = query.where(LlmCall.feature == feature)
    if q:
        pattern = f"%{q}%"
        query = query.where(LlmCall.response.ilike(pattern))
    if after:
        query = query.where(LlmCall.created_at > after)
    if before:
        query = query.where(LlmCall.created_at < before)
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_llm_call(session: AsyncSession, call_id: int) -> LlmCall | None:
    result = await session.execute(select(LlmCall).where(LlmCall.id == call_id))
    return result.scalars().first()
