from collections import defaultdict
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/finance")


@router.get("/", response_class=HTMLResponse)
async def finance_page(request: Request):
    period = request.query_params.get("period", "this month")

    spending, by_category, transactions, budgets, all_txns = None, None, [], [], []
    accounts, categories, recurring, all_budgets, errors = [], [], [], [], []

    try:
        accounts = await api.get("/finance/accounts/", params={"is_active": "true"})
    except httpx.HTTPError:
        pass

    try:
        categories = await api.get("/finance/categories/")
    except httpx.HTTPError:
        pass

    try:
        spending = await api.get("/finance/transactions/report/", params={"period": period})
    except httpx.HTTPError:
        errors.append("spending")

    try:
        by_category = await api.get("/finance/transactions/by-category/", params={"period": period})
    except httpx.HTTPError:
        errors.append("by_category")

    try:
        transactions = await api.get("/finance/transactions/", params={"type": "expense", "limit": 15, "period": period})
    except httpx.HTTPError:
        errors.append("transactions")

    try:
        budgets = await api.get("/finance/budgets/remaining/", params={"period": "monthly"})
    except httpx.HTTPError:
        errors.append("budgets")

    try:
        all_txns = await api.get("/finance/transactions/", params={"type": "expense", "limit": 500, "period": period})
    except httpx.HTTPError:
        pass

    try:
        recurring = await api.get("/finance/recurring-transactions/")
    except httpx.HTTPError:
        pass

    try:
        all_budgets = await api.get("/finance/budgets/")
    except httpx.HTTPError:
        pass

    category_items = (by_category or {}).get("items", [])
    max_total = max((float(i["total"]) for i in category_items), default=1) or 1
    top_category = category_items[0] if category_items else None

    # Budget totals for the "remaining" summary card
    total_budget = sum(float(b["budget_amount"]) for b in budgets) if budgets else None
    total_spent_budget = sum(float(b["spent"]) for b in budgets) if budgets else None
    total_remaining = (total_budget - total_spent_budget) if total_budget is not None else None

    # Spending over time: group by day (month view) or month (year view)
    time_spending: dict[str, float] = defaultdict(float)
    for txn in all_txns:
        key = txn["date"][:7] if period == "this year" else txn["date"][:10]
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

    return templates.TemplateResponse(request, "finance.html", {
        "spending": spending,
        "category_items": category_items,
        "max_total": max_total,
        "top_category": top_category,
        "transactions": transactions,
        "budgets": budgets,
        "total_remaining": total_remaining,
        "period": period,
        "errors": errors,
        "time_spending": time_spending_sorted,
        "category_chart": category_chart,
        "budget_chart": budget_chart,
        "time_label": "Month" if period == "this year" else "Day",
        "accounts": accounts,
        "categories": categories,
        "recurring": recurring,
        "all_budgets": budgets,
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
    period = request.query_params.get("period", "this month")
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
        await api.post("/finance/transactions/", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to create transaction.</p>', status_code=422)

    transactions = []
    try:
        transactions = await api.get("/finance/transactions/", params={"limit": 15, "period": period})
    except httpx.HTTPError:
        pass

    return templates.TemplateResponse(request, "_finance_transactions.html", {"transactions": transactions})


@router.delete("/transactions/{transaction_id}", response_class=Response)
async def delete_transaction(transaction_id: int, request: Request):
    period = request.query_params.get("period", "this month")
    try:
        await api.delete(f"/finance/transactions/{transaction_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete transaction.</p>', status_code=422)

    transactions = []
    try:
        transactions = await api.get("/finance/transactions/", params={"limit": 15, "period": period})
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_transactions.html", {"transactions": transactions})


# --- Accounts ---

@router.post("/accounts", response_class=HTMLResponse)
async def create_account(
    request: Request,
    name: Annotated[str, Form()],
    type: Annotated[str, Form()],
    currency: Annotated[str, Form()] = "EUR",
    institution: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "type": type, "currency": currency}
    if institution:
        payload["institution"] = institution
    try:
        await api.post("/finance/accounts/", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create account.</p>', status_code=422)

    accounts = []
    try:
        accounts = await api.get("/finance/accounts/")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_accounts.html", {"accounts": accounts})


@router.delete("/accounts/{account_id}", response_class=HTMLResponse)
async def delete_account(account_id: int, request: Request):
    try:
        await api.delete(f"/finance/accounts/{account_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete account.</p>', status_code=422)

    accounts = []
    try:
        accounts = await api.get("/finance/accounts/")
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
        await api.post("/finance/categories/", json={"name": name})
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create category.</p>', status_code=422)

    categories = []
    try:
        categories = await api.get("/finance/categories/")
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
        categories = await api.get("/finance/categories/")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_finance_categories.html", {"categories": categories})


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
        await api.post("/finance/budgets/", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create budget.</p>', status_code=422)

    budgets, categories = [], []
    try:
        budgets = await api.get("/finance/budgets/")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories/")
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
        budgets = await api.get("/finance/budgets/")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories/")
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
    recurrence_rule: Annotated[str, Form()],
    category_id: Annotated[Optional[str], Form()] = None,
    currency: Annotated[str, Form()] = "EUR",
):
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
        await api.post("/finance/recurring-transactions/", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create recurring transaction.</p>', status_code=422)

    recurring, accounts, categories = [], [], []
    try:
        recurring = await api.get("/finance/recurring-transactions/")
    except httpx.HTTPError:
        pass
    try:
        accounts = await api.get("/finance/accounts/")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories/")
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
        recurring = await api.get("/finance/recurring-transactions/")
    except httpx.HTTPError:
        pass
    try:
        accounts = await api.get("/finance/accounts/")
    except httpx.HTTPError:
        pass
    try:
        categories = await api.get("/finance/categories/")
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(
        request, "_finance_recurring.html",
        {"recurring": recurring, "accounts": accounts, "categories": categories},
    )
