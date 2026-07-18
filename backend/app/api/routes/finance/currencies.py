from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import CurrencyServiceDep
from app.features.finance.currencies.schemas import CurrencyCreate, CurrencyRead, CurrencyUpdate
from app.features.finance.currencies.service import DuplicateCurrencyError

router = APIRouter(prefix="/finance/currencies", tags=["finance"], dependencies=[Depends(require_auth)])


@router.post("", response_model=CurrencyRead, status_code=status.HTTP_201_CREATED)
async def create_currency(request: CurrencyCreate, service: CurrencyServiceDep):
    try:
        return await service.create(request)
    except DuplicateCurrencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Currency {exc.code} already exists"
        )


@router.get("", response_model=list[CurrencyRead])
async def list_currencies(service: CurrencyServiceDep):
    return await service.list()


@router.get("/{code}", response_model=CurrencyRead)
async def get_currency(code: str, service: CurrencyServiceDep):
    currency = await service.get(code)
    if currency is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found")
    return currency


@router.patch("/{code}", response_model=CurrencyRead)
async def update_currency(code: str, request: CurrencyUpdate, service: CurrencyServiceDep):
    currency = await service.update(code, request)
    if currency is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found")
    return currency


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_currency(code: str, service: CurrencyServiceDep):
    deleted = await service.delete(code)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
