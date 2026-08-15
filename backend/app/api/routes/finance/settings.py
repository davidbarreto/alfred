from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import FinanceSettingsServiceDep
from app.features.finance.settings.schemas import FinanceSettingsRead, FinanceSettingsUpdate

router = APIRouter(prefix="/finance/settings", tags=["finance"], dependencies=[Depends(require_auth)])


@router.get("", response_model=FinanceSettingsRead)
async def get_finance_settings(service: FinanceSettingsServiceDep):
    return await service.get()


@router.put("", response_model=FinanceSettingsRead)
async def update_finance_settings(request: FinanceSettingsUpdate, service: FinanceSettingsServiceDep):
    return await service.update(request)
