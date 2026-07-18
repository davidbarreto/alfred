from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import AccountServiceDep
from app.features.finance.accounts.schemas import AccountCreate, AccountFilters, AccountRead, AccountUpdate
from app.features.finance.accounts.service import AccountDeletionBlockedError

router = APIRouter(prefix="/finance/accounts", tags=["finance"], dependencies=[Depends(require_auth)])


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(request: AccountCreate, service: AccountServiceDep):
    return await service.create(request)


@router.get("", response_model=list[AccountRead])
async def list_accounts(service: AccountServiceDep, filters: AccountFilters = Depends()):
    return await service.list(filters)


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(account_id: int, service: AccountServiceDep):
    account = await service.get(account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(account_id: int, request: AccountUpdate, service: AccountServiceDep):
    account = await service.update(account_id, request)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, service: AccountServiceDep):
    try:
        deleted = await service.delete(account_id)
    except AccountDeletionBlockedError as exc:
        if exc.transaction_count:
            detail = (
                f"Cannot delete this account: it still has {exc.transaction_count} transaction(s). "
                "Deactivate the account instead, or delete its transactions first."
            )
        else:
            detail = (
                "Cannot delete this account: it still has related records (recurring "
                "transactions or import history). Deactivate the account instead."
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
