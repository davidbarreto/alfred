import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.finance.recurring_transactions.schemas import RecurringTransactionFilters
from app.features.finance.recurring_transactions.service import RecurringTransactionService

logger = logging.getLogger(__name__)


async def handle_recurring(command: str, arguments: dict[str, Any], service: RecurringTransactionService) -> Any:
    logger.debug("handle_recurring: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        filters = RecurringTransactionFilters(
            active=arguments.get("active"),
            type=arguments.get("type"),
            account_id=int(arguments["account_id"]) if arguments.get("account_id") else None,
        )
        results = await service.list(filters)
        return [r.model_dump(mode="json") for r in results]

    if command == "get":
        recurring_id = int(arguments["id"])
        result = await service.get(recurring_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recurring transaction {recurring_id} not found")
        return result.model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown recurring command: {command}")
