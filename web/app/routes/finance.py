import html
import json
from collections import defaultdict
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

    spending, by_category, transactions, budgets, all_txns = None, None, [], [], []
    accounts, categories, currencies, recurring, all_budgets, errors = [], [], [], [], [], []

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
            budgets = await api.get("/finance/budgets/remaining", params={"period": "monthly"})
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

    try:
        all_budgets = await api.get("/finance/budgets")
    except httpx.HTTPError:
        pass

    category_items = (by_category or {}).get("items", [])
    max_total = max((float(i["total"]) for i in category_items), default=1) or 1
    top_category = category_items[0] if category_items else None

    # Budget totals for the "remaining" summary card
    total_budget = sum(float(b["budget_amount"]) for b in budgets) if budgets else None
    total_spent_budget = sum(float(b["spent"]) for b in budgets) if budgets else None
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
            "budget": float(b["budget_amount"]),
        }
        for b in (budgets or [])
        if b.get("category_name")
    }

    currency_symbols = {c["code"]: c["symbol"] for c in currencies if c.get("symbol")}

    return templates.TemplateResponse(request, "finance.html", {
        "spending": spending,
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
        "errors": errors,
        "time_spending": time_spending_sorted,
        "category_chart": category_chart,
        "budget_chart": budget_chart,
        "time_label": "Month" if group_by_month else "Day",
        "accounts": accounts,
        "categories": categories,
        "currencies": currencies,
        "recurring": recurring,
        "all_budgets": budgets,
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

@router.post("/budgets", response_class=HTMLResponse)
async def create_budget(
    request: Request,
    name: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    period: Annotated[str, Form()],
    category_id: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "amount": amount, "period": period}
    if category_id:
        payload["category_id"] = int(category_id)
    try:
        await api.post("/finance/budgets", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create budget.</p>', status_code=422)

    budgets, categories = [], []
    try:
        budgets = await api.get("/finance/budgets")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_budgets.html", {"budgets": budgets, "categories": categories})


@router.delete("/budgets/{budget_id}", response_class=HTMLResponse)
async def delete_budget(budget_id: int, request: Request):
    try:
        await api.delete(f"/finance/budgets/{budget_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete budget.</p>', status_code=422)

    budgets, categories = [], []
    try:
        budgets = await api.get("/finance/budgets")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_budgets.html", {"budgets": budgets, "categories": categories})


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


async def _import_rules_context() -> dict:
    rules, categories, accounts = [], [], []
    try:
        rules = await api.get("/finance/imports/rules")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories")
    except httpx.HTTPError:
        pass
    try:
        accounts = await api.get("/finance/accounts")
    except httpx.HTTPError:
        pass
    return {
        "rules": rules,
        "categories": categories,
        "rule_accounts": accounts,
        "categories_by_id": {c["id"]: c["name"] for c in categories},
        "accounts_by_id": {a["id"]: a["name"] for a in accounts},
    }


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


@router.delete("/import/rules/{rule_id}", response_class=HTMLResponse)
async def delete_import_rule(rule_id: int, request: Request):
    try:
        await api.delete(f"/finance/imports/rules/{rule_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete rule.</p>', status_code=422)
    context = await _import_rules_context()
    return templates.TemplateResponse(request, "_finance_import_rules.html", context)


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
