import html
import json
from collections import defaultdict
from datetime import date
from typing import Annotated, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/finance")

_PAGE_SIZE = 20
_IMPORT_COMMIT_TIMEOUT = 60.0


def _parse_txn_query(request: Request) -> tuple[dict, int]:
    qp = request.query_params
    filters = {
        "type": qp.get("type") or None,
        "category_id": qp.get("category_id") or None,
        "account_id": qp.get("account_id") or None,
        "merchant": qp.get("merchant") or None,
        "from_date": qp.get("from_date") or None,
        "to_date": qp.get("to_date") or None,
        "currency": qp.get("currency") or None,
    }
    offset = max(0, int(qp.get("offset", "0") or "0"))
    return filters, offset


def _build_txn_params(filters: dict, offset: int) -> dict:
    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset}
    params.update({k: v for k, v in filters.items() if v})
    return params


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _PAGE_SIZE
    return items[:_PAGE_SIZE], has_next, offset > 0


async def _currency_symbols() -> dict[str, str]:
    try:
        currencies = await api.get("/finance/currencies")
    except httpx.HTTPError:
        return {}
    return {c["code"]: c["symbol"] for c in currencies if c.get("symbol")}


async def _txn_list_context(filters: dict, offset: int) -> dict:
    try:
        raw = await api.get("/finance/transactions", params=_build_txn_params(filters, offset))
    except httpx.HTTPError:
        raw = []
    transactions, has_next, has_prev = _pagination(raw, offset)

    categories, txn_accounts = [], []
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    try:
        txn_accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass

    return {
        "transactions": transactions,
        "has_next": has_next,
        "has_prev": has_prev,
        "categories": categories,
        "accounts": txn_accounts,
        "categories_by_id": {c["id"]: c["name"] for c in categories},
        "accounts_by_id": {a["id"]: a["name"] for a in txn_accounts},
        "currency_symbols": await _currency_symbols(),
        "query_filters": filters,
        "query_offset": offset,
        "page_size": _PAGE_SIZE,
        "filters_qs": urlencode({**{k: v for k, v in filters.items() if v}, "offset": offset}),
    }


_MONTH_GROUPING_THRESHOLD_DAYS = 60


def _range_params(request: Request) -> dict:
    """Resolve the active date range: explicit query params win, otherwise fall back to
    whatever range was last used in this session, otherwise default to this month.
    Whatever is resolved is saved back to the session so the choice survives a new visit.
    """
    qp = request.query_params
    from_date = qp.get("from_date")
    to_date = qp.get("to_date")
    period = qp.get("period")
    if from_date and to_date:
        params = {"from_date": from_date, "to_date": to_date}
    elif period:
        params = {"period": period}
    else:
        params = request.session.get("finance_range") or {"period": "this month"}
    request.session["finance_range"] = params
    return params


def _resolve_currency(request: Request) -> str:
    """Same persistence pattern as _range_params, for the currency toggle."""
    raw = request.query_params.get("currency")
    currency = (raw or request.session.get("finance_currency") or "EUR").upper()
    request.session["finance_currency"] = currency
    return currency


async def _dashboard_txn_list_context(range_params: dict, currency: str) -> dict:
    transactions, categories, txn_accounts = [], [], []
    try:
        transactions = await api.get(
            "/finance/transactions", params={"limit": 15, "currency": currency, **range_params}
        )
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    try:
        txn_accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    return {
        "transactions": transactions,
        "categories_by_id": {c["id"]: c["name"] for c in categories},
        "accounts_by_id": {a["id"]: a["name"] for a in txn_accounts},
        "currency_symbols": await _currency_symbols(),
    }


@router.get("/", response_class=HTMLResponse)
async def finance_page(request: Request):
    range_params = _range_params(request)
    is_custom = "from_date" in range_params
    period = None if is_custom else range_params["period"]
    custom_from = range_params.get("from_date")
    custom_to = range_params.get("to_date")
    range_qs = urlencode(range_params)
    currency = _resolve_currency(request)

    spending, income, by_category, transactions, budgets, all_txns = None, None, None, [], [], []
    accounts, categories, currencies, recurring, errors = [], [], [], [], []

    try:
        accounts = await api.get("/finance/accounts", params={"is_active": "true"})
    except httpx.HTTPError:
        pass

    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass

    try:
        currencies = await api.get("/finance/currencies")
    except httpx.HTTPError:
        pass

    try:
        spending = await api.get("/finance/transactions/report", params={**range_params, "currency": currency})
    except httpx.HTTPError:
        errors.append("spending")

    try:
        income = await api.get("/finance/transactions/income-report", params={**range_params, "currency": currency})
    except httpx.HTTPError:
        errors.append("income")

    try:
        by_category = await api.get("/finance/transactions/by-category", params={**range_params, "currency": currency})
    except httpx.HTTPError:
        errors.append("by_category")

    try:
        transactions = await api.get(
            "/finance/transactions",
            params={"type": "expense", "limit": 15, "currency": currency, **range_params},
        )
    except httpx.HTTPError:
        errors.append("transactions")

    if currency == "EUR":  # budgets are EUR-scoped
        try:
            budgets = await api.get("/finance/budgets/status")
        except httpx.HTTPError:
            errors.append("budgets")

    try:
        all_txns = await api.get(
            "/finance/transactions",
            params={"type": "expense", "limit": 500, "currency": currency, **range_params},
        )
    except httpx.HTTPError:
        pass

    try:
        recurring = await api.get("/finance/recurring-transactions")
    except httpx.HTTPError:
        pass

    category_items = (by_category or {}).get("items", [])
    max_total = max((float(i["total"]) for i in category_items), default=1) or 1
    top_category = category_items[0] if category_items else None

    # Budget totals for the "remaining" summary card
    tracked_budgets = [b for b in (budgets or []) if b.get("limit_amount") is not None]
    total_budget = sum(float(b["limit_amount"]) for b in tracked_budgets) if tracked_budgets else None
    total_spent_budget = sum(float(b["spent"]) for b in tracked_budgets) if tracked_budgets else None
    total_remaining = (total_budget - total_spent_budget) if total_budget is not None else None

    # Spending over time: group by day for short ranges, by month for long ones
    # (year/quarter/semester/wide custom ranges), based on the range the API resolved.
    resolved_from = (spending or {}).get("from_date") or (by_category or {}).get("from_date")
    resolved_to = (spending or {}).get("to_date") or (by_category or {}).get("to_date")
    group_by_month = False
    if resolved_from and resolved_to:
        from datetime import date as _date
        span_days = (_date.fromisoformat(resolved_to) - _date.fromisoformat(resolved_from)).days + 1
        group_by_month = span_days > _MONTH_GROUPING_THRESHOLD_DAYS

    # Query string for "drill down to transactions" links on the summary cards.
    txn_range_qs = urlencode(
        {k: v for k, v in {"from_date": resolved_from, "to_date": resolved_to, "currency": currency}.items() if v}
    )

    time_spending: dict[str, float] = defaultdict(float)
    for txn in all_txns:
        key = txn["date"][:7] if group_by_month else txn["date"][:10]
        time_spending[key] += float(txn["amount"])
    time_spending_sorted = dict(sorted(time_spending.items()))

    # Category chart data
    category_chart = {
        (i["category_name"] or "Uncategorized"): float(i["total"])
        for i in category_items
    }

    # Budget utilization chart data
    budget_chart = {
        b["category_name"]: {
            "spent": float(b["spent"]),
            "budget": float(b["limit_amount"]),
        }
        for b in tracked_budgets
        if b.get("category_name")
    }

    currency_symbols = {c["code"]: c["symbol"] for c in currencies if c.get("symbol")}

    return templates.TemplateResponse(request, "finance.html", {
        "spending": spending,
        "income": income,
        "category_items": category_items,
        "max_total": max_total,
        "top_category": top_category,
        "transactions": transactions,
        "budgets": budgets,
        "total_remaining": total_remaining,
        "period": period,
        "is_custom": is_custom,
        "custom_from": custom_from,
        "custom_to": custom_to,
        "range_qs": range_qs,
        "txn_range_qs": txn_range_qs,
        "errors": errors,
        "time_spending": time_spending_sorted,
        "category_chart": category_chart,
        "budget_chart": budget_chart,
        "time_label": "Month" if group_by_month else "Day",
        "accounts": accounts,
        "categories": categories,
        "currencies": currencies,
        "recurring": recurring,
        "currency": currency,
        "currency_symbol": currency_symbols.get(currency, currency + " "),
        "currency_symbols": currency_symbols,
        "account_currencies": sorted({a["currency"] for a in accounts} | {"EUR"}),
        "accounts_by_id": {a["id"]: a["name"] for a in accounts},
        "categories_by_id": {c["id"]: c["name"] for c in categories},
    })


@router.post("/transactions", response_class=HTMLResponse)
async def create_transaction(
    request: Request,
    amount: Annotated[str, Form()],
    date: Annotated[str, Form()],
    type: Annotated[str, Form()],
    account_id: Annotated[str, Form()],
    category_id: Annotated[Optional[str], Form()] = None,
    merchant: Annotated[Optional[str], Form()] = None,
    description: Annotated[Optional[str], Form()] = None,
):
    range_params = _range_params(request)
    currency = _resolve_currency(request)
    payload: dict = {
        "amount": amount,
        "date": f"{date}T00:00:00",
        "type": type,
        "account_id": int(account_id),
    }
    if category_id:
        payload["category_id"] = int(category_id)
    if merchant:
        payload["merchant"] = merchant
    if description:
        payload["description"] = description

    try:
        await api.post("/finance/transactions", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to create transaction.</p>', status_code=422)

    context = await _dashboard_txn_list_context(range_params, currency)
    return templates.TemplateResponse(request, "_finance_transactions.html", context)


@router.patch("/transactions/{transaction_id}", response_class=HTMLResponse)
async def update_transaction(
    transaction_id: int,
    request: Request,
    amount: Annotated[str, Form()],
    date: Annotated[str, Form()],
    type: Annotated[str, Form()],
    account_id: Annotated[str, Form()],
    category_id: Annotated[Optional[str], Form()] = None,
    merchant: Annotated[Optional[str], Form()] = None,
    description: Annotated[Optional[str], Form()] = None,
    note: Annotated[Optional[str], Form()] = None,
):
    # Every editable field is sent on every save (not just changed ones) so clearing a
    # field (e.g. removing a merchant) actually clears it rather than leaving it untouched.
    payload: dict = {
        "amount": amount,
        "date": f"{date}T00:00:00",
        "type": type,
        "account_id": int(account_id),
        "category_id": int(category_id) if category_id else None,
        "merchant": merchant or None,
        "description": description or None,
        "note": note or None,
    }

    try:
        await api.patch(f"/finance/transactions/{transaction_id}", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to update transaction.</p>', status_code=422)

    if "offset" in request.query_params:
        filters, offset = _parse_txn_query(request)
        context = await _txn_list_context(filters, offset)
        return templates.TemplateResponse(request, "_finance_transactions_list.html", context)

    range_params = _range_params(request)
    currency = _resolve_currency(request)
    context = await _dashboard_txn_list_context(range_params, currency)
    return templates.TemplateResponse(request, "_finance_transactions.html", context)


@router.delete("/transactions/{transaction_id}", response_class=Response)
async def delete_transaction(transaction_id: int, request: Request):
    try:
        await api.delete(f"/finance/transactions/{transaction_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete transaction.</p>', status_code=422)

    if "offset" in request.query_params:
        filters, offset = _parse_txn_query(request)
        context = await _txn_list_context(filters, offset)
        return templates.TemplateResponse(request, "_finance_transactions_list.html", context)

    range_params = _range_params(request)
    currency = _resolve_currency(request)
    context = await _dashboard_txn_list_context(range_params, currency)
    return templates.TemplateResponse(request, "_finance_transactions.html", context)


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request):
    filters, offset = _parse_txn_query(request)
    context = await _txn_list_context(filters, offset)
    return templates.TemplateResponse(request, "finance_transactions.html", context)


@router.get("/transactions/list", response_class=HTMLResponse)
async def transactions_list_fragment(request: Request):
    filters, offset = _parse_txn_query(request)
    context = await _txn_list_context(filters, offset)
    return templates.TemplateResponse(request, "_finance_transactions_list.html", context)


@router.post("/transactions/bulk-move", response_class=Response)
async def bulk_move_transactions(request: Request):
    body = await request.json()
    payload: dict = {
        "account_id": int(body["account_id"]),
        "target_account_id": int(body["target_account_id"]),
    }
    for key in ("type", "merchant", "from_date", "to_date"):
        if body.get(key):
            payload[key] = body[key]
    if body.get("category_id"):
        payload["category_id"] = int(body["category_id"])

    try:
        await api.post("/finance/transactions/bulk-move", json=payload)
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail") or "Failed to move transactions."
        except ValueError:
            detail = "Failed to move transactions."
        return HTMLResponse(detail, status_code=422)
    except httpx.HTTPError:
        return HTMLResponse("Failed to move transactions.", status_code=422)

    return Response(status_code=200)


# --- Accounts ---

@router.post("/accounts", response_class=HTMLResponse)
async def create_account(
    request: Request,
    name: Annotated[str, Form()],
    type: Annotated[str, Form()],
    currency: Annotated[str, Form()] = "EUR",
    institution: Annotated[Optional[str], Form()] = None,
    credit_limit: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "type": type, "currency": currency}
    if institution:
        payload["institution"] = institution
    if credit_limit:
        payload["credit_limit"] = credit_limit
    try:
        await api.post("/finance/accounts", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create account.</p>', status_code=422)

    accounts = []
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_accounts.html", {"accounts": accounts})


@router.delete("/accounts/{account_id}", response_class=HTMLResponse)
async def delete_account(account_id: int, request: Request):
    try:
        await api.delete(f"/finance/accounts/{account_id}")
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail") or "Failed to delete account."
        except ValueError:
            detail = "Failed to delete account."
        return HTMLResponse(f'<p class="text-[#E24B4A] text-sm">{detail}</p>', status_code=422)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete account.</p>', status_code=422)

    accounts = []
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_accounts.html", {"accounts": accounts})


# --- Categories ---

@router.post("/categories", response_class=HTMLResponse)
async def create_category(
    request: Request,
    name: Annotated[str, Form()],
):
    try:
        await api.post("/finance/categories", json={"name": name})
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create category.</p>', status_code=422)

    categories = []
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_categories.html", {"categories": categories})


@router.delete("/categories/{category_id}", response_class=HTMLResponse)
async def delete_category(category_id: int, request: Request):
    try:
        await api.delete(f"/finance/categories/{category_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete category.</p>', status_code=422)

    categories = []
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_categories.html", {"categories": categories})


# --- Currencies ---

@router.post("/currencies", response_class=HTMLResponse)
async def create_currency(
    request: Request,
    code: Annotated[str, Form()],
    symbol: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
):
    try:
        await api.post(
            "/finance/currencies",
            json={"code": code, "symbol": symbol or None, "name": name or None},
        )
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create currency.</p>', status_code=422)

    currencies = []
    try:
        currencies = await api.get("/finance/currencies")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_currencies.html", {"currencies": currencies})


@router.delete("/currencies/{code}", response_class=HTMLResponse)
async def delete_currency(code: str, request: Request):
    try:
        await api.delete(f"/finance/currencies/{code}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete currency.</p>', status_code=422)

    currencies = []
    try:
        currencies = await api.get("/finance/currencies")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_currencies.html", {"currencies": currencies})


# --- Budgets ---

async def _budget_targets_context() -> dict:
    categories, targets, currencies = [], [], []
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    try:
        targets = await api.get("/finance/budgets/targets")
    except httpx.HTTPError:
        pass
    try:
        currencies = await api.get("/finance/currencies")
    except httpx.HTTPError:
        pass
    targets_by_category = {t["category_id"]: t["amount"] for t in targets}
    currency_symbols = {c["code"]: c["symbol"] for c in currencies if c.get("symbol")}
    return {
        "categories": categories,
        "targets_by_category": targets_by_category,
        "currency_symbol": currency_symbols.get("EUR", "€"),
    }


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(request: Request):
    context = await _budget_targets_context()
    year_month = date.today().strftime("%Y-%m")
    budget_status = []
    try:
        budget_status = await api.get("/finance/budgets/status", params={"year_month": year_month})
    except httpx.HTTPError:
        pass
    context.update({"budget_status": budget_status, "year_month": year_month})
    return templates.TemplateResponse(request, "finance_budgets.html", context)


@router.put("/budgets/targets", response_class=HTMLResponse)
async def set_budget_targets(request: Request):
    try:
        body = await request.json()
        items = body["targets"]
    except (ValueError, KeyError, TypeError):
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Invalid payload.</p>', status_code=422)

    try:
        await api.put("/finance/budgets/targets", json={"targets": items})
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to save budgets.</p>', status_code=422)

    context = await _budget_targets_context()
    return templates.TemplateResponse(request, "_finance_budgets_targets.html", context)


@router.get("/budgets/status.json")
async def budget_status_json(year_month: Optional[str] = None):
    params = {"year_month": year_month} if year_month else {}
    try:
        status = await api.get("/finance/budgets/status", params=params)
    except httpx.HTTPError:
        status = []
    return status


# --- Recurring transactions ---

@router.post("/recurring", response_class=HTMLResponse)
async def create_recurring(
    request: Request,
    merchant: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    type: Annotated[str, Form()],
    account_id: Annotated[str, Form()],
    recurrence_freq: Annotated[str, Form()],
    category_id: Annotated[Optional[str], Form()] = None,
    currency: Annotated[str, Form()] = "EUR",
    stop_date: Annotated[Optional[str], Form()] = None,
):
    recurrence_rule = recurrence_freq
    if stop_date:
        recurrence_rule += f";UNTIL={stop_date.replace('-', '')}"
    payload: dict = {
        "merchant": merchant,
        "amount": amount,
        "type": type,
        "account_id": int(account_id),
        "recurrence_rule": recurrence_rule,
        "currency": currency,
    }
    if category_id:
        payload["category_id"] = int(category_id)
    try:
        await api.post("/finance/recurring-transactions", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create recurring transaction.</p>', status_code=422)

    recurring, accounts, categories = [], [], []
    try:
        recurring = await api.get("/finance/recurring-transactions")
    except httpx.HTTPError:
        pass
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(
        request, "_finance_recurring.html",
        {"recurring": recurring, "accounts": accounts, "categories": categories},
    )


@router.delete("/recurring/{recurring_id}", response_class=HTMLResponse)
async def delete_recurring(recurring_id: int, request: Request):
    try:
        await api.delete(f"/finance/recurring-transactions/{recurring_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete recurring transaction.</p>', status_code=422)

    recurring, accounts, categories = [], [], []
    try:
        recurring = await api.get("/finance/recurring-transactions")
    except httpx.HTTPError:
        pass
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(
        request, "_finance_recurring.html",
        {"recurring": recurring, "accounts": accounts, "categories": categories},
    )


# --- Statement import ---

async def _import_batches_context() -> dict:
    batches, accounts = [], []
    try:
        batches = await api.get("/finance/imports")
    except httpx.HTTPError:
        pass
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    return {
        "batches": batches,
        "accounts_by_id": {a["id"]: a["name"] for a in accounts},
    }


_RULES_CARD_LIMIT = 5
_RULES_PAGE_SIZE = 20


async def _import_rules_shared_context() -> dict:
    categories, accounts = [], []
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    return {
        "categories": categories,
        "rule_accounts": accounts,
        "categories_by_id": {c["id"]: c["name"] for c in categories},
        "accounts_by_id": {a["id"]: a["name"] for a in accounts},
    }


async def _import_rules_context() -> dict:
    """Context for the small rules card on the import page: latest 5, no filters."""
    rules = []
    try:
        rules = await api.get("/finance/imports/rules", params={"limit": _RULES_CARD_LIMIT})
    except httpx.HTTPError:
        pass
    context = await _import_rules_shared_context()
    context.update({"rules": rules, "rules_delete_target": "#import-rules", "rules_filters_qs": ""})
    return context


def _parse_rule_query(request: Request) -> tuple[dict, int]:
    qp = request.query_params
    filters = {
        "pattern": qp.get("pattern") or None,
        "mode": qp.get("mode") or None,
        "category_id": qp.get("category_id") or None,
    }
    offset = max(0, int(qp.get("offset", "0") or "0"))
    return filters, offset


def _build_rule_params(filters: dict, offset: int) -> dict:
    params: dict = {"limit": _RULES_PAGE_SIZE + 1, "offset": offset, "sort": "precedence"}
    params.update({k: v for k, v in filters.items() if v})
    return params


def _rule_pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _RULES_PAGE_SIZE
    return items[:_RULES_PAGE_SIZE], has_next, offset > 0


async def _import_rules_page_context(filters: dict, offset: int) -> dict:
    """Context for the full, filterable, paginated rules page ("See all")."""
    try:
        raw = await api.get("/finance/imports/rules", params=_build_rule_params(filters, offset))
    except httpx.HTTPError:
        raw = []
    rules, has_next, has_prev = _rule_pagination(raw, offset)
    context = await _import_rules_shared_context()
    context.update({
        "rules": rules,
        "has_next": has_next,
        "has_prev": has_prev,
        "query_filters": filters,
        "query_offset": offset,
        "page_size": _RULES_PAGE_SIZE,
        "rules_delete_target": "#import-rules-full",
        "rules_filters_qs": urlencode({**{k: v for k, v in filters.items() if v}, "offset": offset}),
        "show_reorder": True,
    })
    return context


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    accounts, providers, grouped_providers = [], [], []
    try:
        accounts = await api.get("/finance/accounts", params={"is_active": "true"})
    except httpx.HTTPError:
        pass
    try:
        providers = await api.get("/finance/imports/providers")
    except httpx.HTTPError:
        pass
    try:
        grouped_providers = await api.get("/finance/imports/providers-grouped")
    except httpx.HTTPError:
        pass

    context = await _import_batches_context()
    context.update(await _import_rules_context())
    context.update({"accounts": accounts, "providers": providers, "grouped_providers": grouped_providers})
    return templates.TemplateResponse(request, "finance_import.html", context)


@router.get("/import/rules", response_class=HTMLResponse)
async def import_rules_fragment(request: Request):
    context = await _import_rules_context()
    return templates.TemplateResponse(request, "_finance_import_rules.html", context)


@router.post("/import/rules", response_class=HTMLResponse)
async def create_import_rule(
    request: Request,
    pattern: Annotated[str, Form()],
    mode: Annotated[str, Form()] = "auto",
    amount: Annotated[Optional[str], Form()] = None,
    description: Annotated[Optional[str], Form()] = None,
    merchant: Annotated[Optional[str], Form()] = None,
    category_id: Annotated[Optional[str], Form()] = None,
    transfer_account_id: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"pattern": pattern.strip(), "mode": mode}
    if amount:
        payload["amount"] = amount.replace(",", ".").strip()
    if description:
        payload["description"] = description.strip()
    if merchant:
        payload["merchant"] = merchant.strip()
    if category_id:
        payload["category_id"] = int(category_id)
    if transfer_account_id:
        payload["transfer_account_id"] = int(transfer_account_id)

    try:
        await api.post("/finance/imports/rules", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to create rule.</p>', status_code=422)

    context = await _import_rules_context()
    return templates.TemplateResponse(request, "_finance_import_rules.html", context)


@router.patch("/import/rules/{rule_id}", response_class=HTMLResponse)
async def update_import_rule(
    rule_id: int,
    request: Request,
    pattern: Annotated[str, Form()],
    mode: Annotated[str, Form()] = "auto",
    amount: Annotated[Optional[str], Form()] = None,
    description: Annotated[Optional[str], Form()] = None,
    category_id: Annotated[Optional[str], Form()] = None,
    transfer_account_id: Annotated[Optional[str], Form()] = None,
):
    # Every editable field is sent on every save (not just changed ones) so clearing a
    # field (e.g. removing the category) actually clears it rather than leaving it untouched.
    payload: dict = {
        "pattern": pattern.strip(),
        "mode": mode,
        "amount": amount.replace(",", ".").strip() if amount else None,
        "description": description.strip() if description else None,
        "category_id": int(category_id) if category_id else None,
        "transfer_account_id": int(transfer_account_id) if transfer_account_id else None,
    }
    try:
        rule = await api.patch(f"/finance/imports/rules/{rule_id}", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to update rule.</p>', status_code=422)

    context = await _import_rules_shared_context()
    if "offset" in request.query_params:
        filters, offset = _parse_rule_query(request)
        context["rules_delete_target"] = "#import-rules-full"
        context["rules_filters_qs"] = urlencode({**{k: v for k, v in filters.items() if v}, "offset": offset})
        context["show_reorder"] = True
    else:
        context["rules_delete_target"] = "#import-rules"
        context["rules_filters_qs"] = ""
    context["rule"] = rule
    return templates.TemplateResponse(request, "_finance_import_rule_row.html", context)


@router.post("/import/rules/reorder", response_class=HTMLResponse)
async def reorder_import_rules(request: Request):
    try:
        body = await request.json()
        rule_ids = [int(rid) for rid in body["rule_ids"]]
    except (ValueError, KeyError, TypeError):
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Invalid reorder payload.</p>', status_code=422)

    try:
        await api.post("/finance/imports/rules/reorder", json={"rule_ids": rule_ids})
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to save order.</p>', status_code=422)

    filters, offset = _parse_rule_query(request)
    context = await _import_rules_page_context(filters, offset)
    return templates.TemplateResponse(request, "_finance_import_rules_list.html", context)


@router.delete("/import/rules/{rule_id}", response_class=HTMLResponse)
async def delete_import_rule(rule_id: int, request: Request):
    try:
        await api.delete(f"/finance/imports/rules/{rule_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete rule.</p>', status_code=422)

    if "offset" in request.query_params:
        filters, offset = _parse_rule_query(request)
        context = await _import_rules_page_context(filters, offset)
        return templates.TemplateResponse(request, "_finance_import_rules_list.html", context)

    context = await _import_rules_context()
    return templates.TemplateResponse(request, "_finance_import_rules.html", context)


@router.get("/import/rules/all", response_class=HTMLResponse)
async def import_rules_page(request: Request):
    filters, offset = _parse_rule_query(request)
    context = await _import_rules_page_context(filters, offset)
    return templates.TemplateResponse(request, "finance_import_rules.html", context)


@router.get("/import/rules/all/list", response_class=HTMLResponse)
async def import_rules_list_fragment(request: Request):
    filters, offset = _parse_rule_query(request)
    context = await _import_rules_page_context(filters, offset)
    return templates.TemplateResponse(request, "_finance_import_rules_list.html", context)


@router.get("/import/batches", response_class=HTMLResponse)
async def import_batches_fragment(request: Request):
    context = await _import_batches_context()
    return templates.TemplateResponse(request, "_finance_import_batches.html", context)


@router.post("/import/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    account_id: Annotated[str, Form()] = "",
    provider: Annotated[Optional[str], Form()] = None,
):
    content = await file.read()
    data: dict = {"account_id": account_id}
    if provider:
        data["provider"] = provider
    try:
        preview = await api.post_multipart(
            "/finance/imports/preview",
            data=data,
            files={"file": (file.filename or "statement.csv", content, file.content_type or "text/csv")},
        )
    except httpx.HTTPStatusError as exc:
        detail = html.escape(
            _extract_error_detail(exc, "Could not parse this file. Check that it is a supported bank statement export.")
        )
        return HTMLResponse(f'<p class="text-[#E24B4A] text-sm px-1">{detail}</p>', status_code=422)
    except httpx.HTTPError:
        return HTMLResponse(
            '<p class="text-[#E24B4A] text-sm px-1">Could not parse this file. '
            'Check that it is a supported bank statement export.</p>',
            status_code=422,
        )

    accounts, categories = [], []
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass

    return templates.TemplateResponse(
        request, "_finance_import_review.html",
        {
            "preview": preview,
            "accounts": accounts,
            "categories": categories,
            "accounts_by_id": {a["id"]: a["name"] for a in accounts},
        },
    )


def _form_value(form, key: str, default: str = "") -> str:
    value = form.get(key)
    return value if isinstance(value, str) else default


def _extract_error_detail(exc: httpx.HTTPStatusError, fallback: str) -> str:
    """Surface the backend's actual error instead of a flat generic message --
    FastAPI validation failures return `detail` as a list of {loc, msg} objects,
    HTTPException-raised errors return it as a plain string."""
    try:
        body = exc.response.json()
    except ValueError:
        return fallback
    detail = body.get("detail")
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            loc = ".".join(str(p) for p in item.get("loc", []) if p != "body")
            msg = item.get("msg", "")
            parts.append(f"{loc}: {msg}" if loc else msg)
        return "; ".join(parts) or fallback
    return fallback


def _timeout_response() -> HTMLResponse:
    # A timeout here doesn't mean the import failed -- the backend commits the batch
    # in one transaction before the (potentially slow) post-commit embedding step, so
    # the rows may already be saved even though this request gave up waiting.
    return HTMLResponse(
        '<p class="text-[#E24B4A] text-sm px-1">Import is taking longer than expected. '
        "It may have completed on the server — check the import history below before retrying.</p>",
        status_code=422,
    )


@router.post("/import/commit", response_class=HTMLResponse)
async def import_commit(request: Request):
    # JSON, not multipart/form-data: statements with >~75 rows produce more
    # form fields than Starlette's request.form() field-count cap allows.
    try:
        form = await request.json()
    except ValueError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Invalid import payload.</p>', status_code=422)
    rows = []
    row_count = int(_form_value(form, "row_count", "0") or "0")
    for i in range(row_count):
        if f"include_{i}" not in form:
            continue
        row: dict = {
            "date_posted": _form_value(form, f"date_{i}"),
            "bank_description": _form_value(form, f"bank_description_{i}"),
            "amount": _form_value(form, f"amount_{i}"),
            "type": _form_value(form, f"type_{i}"),
            "deduplication_hash": _form_value(form, f"hash_{i}"),
        }
        for field in ("description", "merchant", "note"):
            value = _form_value(form, f"{field}_{i}").strip()
            if value:
                row[field] = value
        category_id = _form_value(form, f"category_{i}")
        if category_id:
            row["category_id"] = int(category_id)
        counterpart = _form_value(form, f"counterpart_{i}")
        if counterpart:
            row["counterpart_account_id"] = int(counterpart)
        if f"save_rule_{i}" in form:
            pattern = _form_value(form, f"rule_pattern_{i}").strip()
            if pattern:
                row["save_rule"] = True
                row["rule_pattern"] = pattern
                row["rule_mode"] = _form_value(form, f"rule_mode_{i}", "auto")
                if _form_value(form, f"rule_match_amount_{i}"):
                    row["rule_match_amount"] = True
        rows.append(row)

    payload: dict = {
        "account_id": int(_form_value(form, "account_id", "0")),
        "provider": _form_value(form, "provider"),
        "source_file": _form_value(form, "source_file") or None,
        "stored_file": _form_value(form, "stored_file") or None,
        "currency": _form_value(form, "currency", "EUR") or "EUR",
        "period_start": _form_value(form, "period_start") or None,
        "period_end": _form_value(form, "period_end") or None,
        "closing_balance": _form_value(form, "closing_balance") or None,
        "rows": rows,
    }
    try:
        result = await api.post("/finance/imports/commit", json=payload, timeout=_IMPORT_COMMIT_TIMEOUT)
    except httpx.HTTPStatusError as exc:
        detail = html.escape(_extract_error_detail(exc, "Import failed."))
        return HTMLResponse(f'<p class="text-[#E24B4A] text-sm px-1">{detail}</p>', status_code=422)
    except httpx.TimeoutException:
        return _timeout_response()
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Import failed.</p>', status_code=422)

    return templates.TemplateResponse(request, "_finance_import_result.html", {"result": result})


@router.post("/import/detect-currencies", response_class=HTMLResponse)
async def import_detect_currencies(
    request: Request,
    file: UploadFile = File(...),
    provider: Annotated[str, Form()] = "",
):
    content = await file.read()
    try:
        detection = await api.post_multipart(
            "/finance/imports/detect-currencies",
            data={"provider": provider},
            files={"file": (file.filename or "statement.csv", content, file.content_type or "text/csv")},
        )
    except httpx.HTTPStatusError as exc:
        detail = html.escape(_extract_error_detail(exc, "Could not read this file."))
        return HTMLResponse(f'<p class="text-[#E24B4A] text-sm px-1">{detail}</p>', status_code=422)
    except httpx.HTTPError:
        return HTMLResponse(
            '<p class="text-[#E24B4A] text-sm px-1">Could not read this file.</p>', status_code=422
        )

    return templates.TemplateResponse(
        request, "_finance_import_currency_map.html", {"detection": detection}
    )


@router.post("/import/preview-grouped", response_class=HTMLResponse)
async def import_preview_grouped(
    request: Request,
    file: UploadFile = File(...),
    provider: Annotated[str, Form()] = "",
    account_map: Annotated[str, Form()] = "{}",
):
    content = await file.read()
    try:
        preview = await api.post_multipart(
            "/finance/imports/preview-grouped",
            data={"provider": provider, "account_map": account_map},
            files={"file": (file.filename or "statement.csv", content, file.content_type or "text/csv")},
        )
    except httpx.HTTPStatusError as exc:
        detail = html.escape(_extract_error_detail(exc, "Could not preview this import."))
        return HTMLResponse(f'<p class="text-[#E24B4A] text-sm px-1">{detail}</p>', status_code=422)
    except httpx.HTTPError:
        return HTMLResponse(
            '<p class="text-[#E24B4A] text-sm px-1">Could not preview this import.</p>', status_code=422
        )

    categories = []
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass

    return templates.TemplateResponse(
        request, "_finance_import_review_grouped.html", {"preview": preview, "categories": categories}
    )


@router.post("/import/commit-grouped", response_class=HTMLResponse)
async def import_commit_grouped(request: Request):
    try:
        form = await request.json()
    except ValueError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Invalid import payload.</p>', status_code=422)

    rows = []
    row_count = int(_form_value(form, "row_count", "0") or "0")
    for i in range(row_count):
        if f"include_{i}" not in form:
            continue
        row: dict = {
            "date_posted": _form_value(form, f"date_{i}"),
            "bank_description": _form_value(form, f"bank_description_{i}"),
            "amount": _form_value(form, f"amount_{i}"),
            "type": _form_value(form, f"type_{i}"),
            "currency": _form_value(form, f"currency_{i}"),
            "deduplication_hash": _form_value(form, f"hash_{i}"),
        }
        for field in ("description", "merchant", "note"):
            value = _form_value(form, f"{field}_{i}").strip()
            if value:
                row[field] = value
        category_id = _form_value(form, f"category_{i}")
        if category_id:
            row["category_id"] = int(category_id)
        counterpart = _form_value(form, f"counterpart_{i}")
        if counterpart:
            row["counterpart_account_id"] = int(counterpart)
        if f"save_rule_{i}" in form:
            pattern = _form_value(form, f"rule_pattern_{i}").strip()
            if pattern:
                row["save_rule"] = True
                row["rule_pattern"] = pattern
                row["rule_mode"] = _form_value(form, f"rule_mode_{i}", "auto")
                if _form_value(form, f"rule_match_amount_{i}"):
                    row["rule_match_amount"] = True
        rows.append(row)

    try:
        account_map = json.loads(_form_value(form, "account_map", "{}"))
    except json.JSONDecodeError:
        account_map = {}

    payload: dict = {
        "provider": _form_value(form, "provider"),
        "source_file": _form_value(form, "source_file") or None,
        "stored_file": _form_value(form, "stored_file") or None,
        "account_map": account_map,
        "rows": rows,
    }
    try:
        result = await api.post(
            "/finance/imports/commit-grouped", json=payload, timeout=_IMPORT_COMMIT_TIMEOUT
        )
    except httpx.HTTPStatusError as exc:
        detail = html.escape(_extract_error_detail(exc, "Import failed."))
        return HTMLResponse(f'<p class="text-[#E24B4A] text-sm px-1">{detail}</p>', status_code=422)
    except httpx.TimeoutException:
        return _timeout_response()
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Import failed.</p>', status_code=422)

    return templates.TemplateResponse(request, "_finance_import_result_grouped.html", {"result": result})


@router.get("/import/batches/{batch_id}/file")
async def download_import_batch_file(batch_id: int):
    try:
        content, content_type = await api.get_bytes(f"/finance/imports/{batch_id}/file")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">File not available.</p>', status_code=404)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="statement-batch-{batch_id}.csv"'},
    )


@router.delete("/import/batches/{batch_id}", response_class=HTMLResponse)
async def delete_import_batch(batch_id: int, request: Request):
    try:
        await api.delete(f"/finance/imports/{batch_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete import batch.</p>', status_code=422)
    context = await _import_batches_context()
    return templates.TemplateResponse(request, "_finance_import_batches.html", context)
