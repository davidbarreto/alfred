from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.db.session import get_session
from app.integrations.llm_calls.repository import get_llm_call, get_llm_calls
from app.integrations.llm_calls.schemas import LlmCallRead

router = APIRouter(
    prefix="/integration/llm-calls",
    tags=["integrations"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[LlmCallRead])
async def read_llm_calls(
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    feature: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Search in response text"),
    after: datetime | None = Query(default=None, description="Return calls created after this timestamp"),
    before: datetime | None = Query(default=None, description="Return calls created before this timestamp"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    return await get_llm_calls(
        session,
        provider=provider,
        model=model,
        feature=feature,
        q=q,
        after=after,
        before=before,
        skip=skip,
        limit=limit,
    )


@router.get("/{call_id}", response_model=LlmCallRead)
async def read_llm_call(call_id: int, session: AsyncSession = Depends(get_session)):
    call = await get_llm_call(session, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="LLM call not found")
    return call
