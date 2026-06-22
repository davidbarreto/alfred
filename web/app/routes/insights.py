from collections import Counter

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/insights")


@router.get("/", response_class=HTMLResponse)
async def insights_page(request: Request):
    memories, llm_calls, provider_calls, cmd_executions = [], [], [], []

    for path, params, target in [
        ("/core/memories/", {"limit": 200}, "memories"),
        ("/integration/llm-calls/", {"limit": 200}, "llm_calls"),
        ("/integration/provider-calls/", {"limit": 200}, "provider_calls"),
        ("/core/command-executions/", {"limit": 200}, "cmd_executions"),
    ]:
        try:
            result = await api.get(path, params=params)
            if target == "memories":
                memories = result
            elif target == "llm_calls":
                llm_calls = result
            elif target == "provider_calls":
                provider_calls = result
            else:
                cmd_executions = result
        except httpx.HTTPError:
            pass

    # LLM aggregations
    llm_by_model = dict(Counter(c["model"] for c in llm_calls).most_common())
    llm_by_feature = dict(Counter(c["feature"] for c in llm_calls).most_common(10))
    total_tokens_in = sum(c.get("tokens_input") or 0 for c in llm_calls)
    total_tokens_out = sum(c.get("tokens_output") or 0 for c in llm_calls)
    avg_latency = (
        sum(c.get("latency_ms") or 0 for c in llm_calls) / len(llm_calls)
        if llm_calls else 0
    )

    # Provider call aggregations
    provider_by_name = dict(Counter(c["provider"] for c in provider_calls).most_common())
    provider_by_status = dict(Counter(c["status"] for c in provider_calls).most_common())

    # Command execution aggregations
    cmd_by_name = dict(Counter(c["command_name"] for c in cmd_executions).most_common(10))
    cmd_by_status = dict(Counter(c["status"] for c in cmd_executions).most_common())

    # Memory aggregations
    memories_by_category = dict(Counter(m["category"] for m in memories).most_common())

    return templates.TemplateResponse(request, "insights.html", {
        "memories": memories,
        "llm_calls": llm_calls[:20],
        "provider_calls": provider_calls[:20],
        # stat cards
        "total_memories": len(memories),
        "total_llm_calls": len(llm_calls),
        "total_tokens": total_tokens_in + total_tokens_out,
        "total_provider_calls": len(provider_calls),
        # chart data (dicts → JSON in template)
        "llm_by_model": llm_by_model,
        "llm_by_feature": llm_by_feature,
        "provider_by_name": provider_by_name,
        "provider_by_status": provider_by_status,
        "cmd_by_name": cmd_by_name,
        "cmd_by_status": cmd_by_status,
        "memories_by_category": memories_by_category,
        # derived
        "avg_latency_ms": round(avg_latency),
    })
