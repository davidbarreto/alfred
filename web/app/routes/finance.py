import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/finance")


@router.get("/", response_class=HTMLResponse)
async def finance_page(request: Request):
    period = request.query_params.get("period", "this month")

    spending, by_category, transactions, budgets = None, None, [], []
    errors = []

    try:
        spending = await api.get("/finance/transactions/report", params={"period": period})
    except httpx.HTTPError:
        errors.append("spending")

    try:
        by_category = await api.get("/finance/transactions/by-category", params={"period": period})
    except httpx.HTTPError:
        errors.append("by_category")

    try:
        transactions = await api.get("/finance/transactions", params={"type": "expense", "limit": 15, "period": period})
    except httpx.HTTPError:
        errors.append("transactions")

    try:
        budgets = await api.get("/finance/budgets/remaining", params={"period": "monthly"})
    except httpx.HTTPError:
        errors.append("budgets")

    category_items = (by_category or {}).get("items", [])
    max_total = max((float(i["total"]) for i in category_items), default=1) or 1
    top_category = category_items[0] if category_items else None

    # Budget totals for the "remaining" summary card
    total_budget = sum(float(b["budget_amount"]) for b in budgets) if budgets else None
    total_spent_budget = sum(float(b["spent"]) for b in budgets) if budgets else None
    total_remaining = (total_budget - total_spent_budget) if total_budget is not None else None

    return templates.TemplateResponse("finance.html", {
        "request": request,
        "spending": spending,
        "category_items": category_items,
        "max_total": max_total,
        "top_category": top_category,
        "transactions": transactions,
        "budgets": budgets,
        "total_remaining": total_remaining,
        "period": period,
        "errors": errors,
    })
