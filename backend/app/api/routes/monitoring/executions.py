from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.db.session import get_session
from app.features.monitoring.repository import get_all_executions
from app.features.monitoring.schemas import ExecutionFilters, ExecutionRead

router = APIRouter(prefix="/monitoring/executions", tags=["monitoring"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[ExecutionRead])
async def list_executions(
    filters: ExecutionFilters = Depends(),
    session: AsyncSession = Depends(get_session),
):
    return await get_all_executions(session=session, filters=filters)
