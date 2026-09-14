import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.finance.accounts.schemas import AccountFilters
from app.features.finance.accounts.service import AccountService

logger = logging.getLogger(__name__)


async def handle_account(command: str, arguments: dict[str, Any], service: AccountService) -> Any:
    logger.debug("handle_account: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        filters = AccountFilters(
            is_active=arguments.get("is_active"),
            type=arguments.get("type"),
            currency=arguments.get("currency"),
        )
        results = await service.list(filters)
        return [r.model_dump(mode="json") for r in results]

    if command == "get":
        account_id = int(arguments["id"])
        result = await service.get(account_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Account {account_id} not found")
        return result.model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown account command: {command}")
