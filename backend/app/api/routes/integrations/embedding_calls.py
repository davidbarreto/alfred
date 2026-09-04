from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.db.session import get_session
from app.integrations.embedding_calls.repository import (
    get_distinct_features,
    get_embedding_call,
    get_embedding_calls,
)
from app.integrations.embedding_calls.schemas import EmbeddingCallRead

router = APIRouter(
    prefix="/integration/embedding-calls",
    tags=["integrations"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[EmbeddingCallRead])
async def read_embedding_calls(
    feature: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Search in query text"),
    after: datetime | None = Query(default=None, description="Return calls created after this timestamp"),
    before: datetime | None = Query(default=None, description="Return calls created before this timestamp"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    return await get_embedding_calls(
        session,
        feature=feature,
        q=q,
        after=after,
        before=before,
        skip=skip,
        limit=limit,
    )


@router.get("/features", response_model=list[str])
async def read_embedding_call_features(session: AsyncSession = Depends(get_session)):
    return await get_distinct_features(session)


@router.get("/{call_id}", response_model=EmbeddingCallRead)
async def read_embedding_call(call_id: int, session: AsyncSession = Depends(get_session)):
    call = await get_embedding_call(session, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Embedding call not found")
    return call
