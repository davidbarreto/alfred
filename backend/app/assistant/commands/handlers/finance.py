import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import parse_dt

logger = logging.getLogger(__name__)
from app.features.finance.accounts.schemas import AccountFilters
from app.features.finance.accounts.service import AccountService
from app.features.finance.budgets.service import BudgetTargetService
from app.features.finance.categories.service import CategoryService
from app.features.finance.recurring_transactions.schemas import RecurringTransactionFilters
from app.features.finance.recurring_transactions.service import RecurringTransactionService
from app.features.finance.transactions.schemas import (
    AnalyticsFilters,
    BalanceForecastResponse,
    TransactionCreate,
    TransactionFilters,
    TransactionUpdate,
)
from app.features.finance.transactions.service import TransactionService


def _parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _parse_date(value: str | None) -> date | None:
    dt = parse_dt(value)
    return dt.date() if dt else None


async def _resolve_account_id(account_name: str | None, service: AccountService) -> int:
    accounts = await service.list(AccountFilters(is_active=True))
    if not accounts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active accounts found")
    if account_name:
        match = next((a for a in accounts if account_name.lower() in a.name.lower()), None)
        if match:
            return match.id
    return accounts[0].id


async def _resolve_category_id(category_name: str | None, service: CategoryService) -> int:
    if not category_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A category is required")
    categories = await service.list()
    match = next((c for c in categories if category_name.lower() in c.name.lower()), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Category not found: {category_name}")
    return match.id


def _resolve_year_month(period: str | None) -> date:
    if not period:
        return date.today().replace(day=1)
    dt = parse_dt(period)
    return dt.date().replace(day=1) if dt else date.today().replace(day=1)


async def handle_finance(
    command: str,
    arguments: dict[str, Any],
    transaction_service: TransactionService,
    account_service: AccountService,
    budget_service: BudgetTargetService,
    recurring_service: RecurringTransactionService,
    category_service: CategoryService,
) -> Any:
    logger.debug("handle_finance: command=%s args_keys=%s", command, list(arguments.keys()))

    # --- Transactions ---

    if command == "transaction_add":
        account_id = await _resolve_account_id(arguments.get("account"), account_service)
        amount = _parse_decimal(arguments.get("amount"))
        txn_date = parse_dt(arguments.get("date")) or parse_dt(arguments.get("deadline"))
        payload = TransactionCreate(
            account_id=account_id,
            date=txn_date or __import__("datetime").datetime.now(),
            amount=amount or Decimal("0"),
            currency=arguments.get("currency", "EUR"),
            type=arguments.get("type", "expense"),
            description=arguments.get("description"),
            merchant=arguments.get("merchant"),
        )
        result = await transaction_service.create(payload)
        return result.model_dump(mode='json')

    if command == "transaction_list":
        filters = TransactionFilters(
            limit=int(arguments.get("limit", 100)),
            type=arguments.get("type"),
            merchant=arguments.get("merchant"),
            from_date=_parse_date(arguments.get("from_date")),
            to_date=_parse_date(arguments.get("to_date")),
            period=arguments.get("period"),
        )
        results = await transaction_service.list(filters)
        return [r.model_dump(mode='json') for r in results]

    if command == "transaction_update":
        txn_id = int(arguments["id"])
        update_fields: dict[str, Any] = {}
        if "amount" in arguments:
            update_fields["amount"] = _parse_decimal(arguments["amount"])
        if "type" in arguments:
            update_fields["type"] = arguments["type"]
        if "merchant" in arguments:
            update_fields["merchant"] = arguments["merchant"]
        if "description" in arguments:
            update_fields["description"] = arguments["description"]
        if "date" in arguments:
            update_fields["date"] = parse_dt(arguments["date"])
        if "currency" in arguments:
            update_fields["currency"] = arguments["currency"]
        result = await transaction_service.update(txn_id, TransactionUpdate(**update_fields))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Transaction {txn_id} not found")
        return result.model_dump(mode='json')

    if command == "transaction_delete":
        txn_id = int(arguments["id"])
        deleted = await transaction_service.delete(txn_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Transaction {txn_id} not found")
        return {"deleted": True, "id": txn_id}

    # --- Budgets ---

    if command == "budget_set":
        category_id = await _resolve_category_id(arguments.get("category"), category_service)
        amount = _parse_decimal(arguments.get("amount"))
        result = await budget_service.set_target(category_id, amount)
        if result is None:
            return {"category_id": category_id, "amount": None, "cleared": True}
        return result.model_dump(mode='json')

    if command == "budget_status":
        year_month = _resolve_year_month(arguments.get("period"))
        results = await budget_service.get_status(year_month)
        if arguments.get("category"):
            category_id = await _resolve_category_id(arguments["category"], category_service)
            results = [r for r in results if r.category_id == category_id]
        return [r.model_dump(mode='json') for r in results]

    # --- Analytics ---

    if command in ("spending_report", "spending_average", "spending_top"):
        filters = AnalyticsFilters(
            period=arguments.get("period"),
            from_date=_parse_date(arguments.get("from_date")),
            to_date=_parse_date(arguments.get("to_date")),
            merchant=arguments.get("merchant"),
            top_n=int(arguments.get("top_n", 5)),
        )
        if command == "spending_report":
            result = await transaction_service.spending_report(filters)
        elif command == "spending_average":
            result = await transaction_service.spending_average(filters)
        else:
            result = await transaction_service.spending_top(filters)
        return result.model_dump(mode='json')

    if command == "balance_forecast":
        filters = AnalyticsFilters(period=arguments.get("period"))
        accounts = await account_service.list(AccountFilters(is_active=True))
        current_balance = sum(a.balance for a in accounts) if accounts else Decimal("0")
        active_recurring = await recurring_service.list(RecurringTransactionFilters(active=True))
        projected_income, projected_expenses, forecast_to = await transaction_service.balance_forecast(
            filters=filters,
            recurring_transactions=active_recurring,
        )
        return BalanceForecastResponse(
            current_balance=current_balance,
            projected_income=projected_income.quantize(Decimal("0.01")),
            projected_expenses=projected_expenses.quantize(Decimal("0.01")),
            projected_balance=(current_balance + projected_income - projected_expenses).quantize(Decimal("0.01")),
            currency="EUR",
            forecast_to=forecast_to,
        ).model_dump(mode='json')

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown finance command: {command}")
