from collections import Counter, defaultdict
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/insights")

_PAGE_SIZE = 20
_PREVIEW_SIZE = 5
_LLM_CALLS_PREVIEW_SIZE = 5
_LLM_CALL_OPTIONS_LIMIT = 500
_PROVIDER_CALLS_PREVIEW_SIZE = 5
_PROVIDER_CALL_OPTIONS_LIMIT = 500
_EMBEDDING_CALLS_PREVIEW_SIZE = 5
_EMBEDDING_CALL_OPTIONS_LIMIT = 500
_MESSAGES_PREVIEW_SIZE = 5
_SESSIONS_PREVIEW_SIZE = 5
_FILTER_OPTIONS_SAMPLE_LIMIT = 200
_MESSAGE_ROLES = ["user", "assistant"]
_MESSAGE_SOURCES = ["telegram", "api", "web"]
_SESSION_SOURCES = ["telegram", "api", "web"]


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    """Return (page_slice, has_next, has_prev) using the limit+1 trick."""
    has_next = len(items) > _PAGE_SIZE
    return items[:_PAGE_SIZE], has_next, offset > 0


_REMINDER_KIND_PATHS = {"task": "/organizer/tasks", "event": "/organizer/calendar-events"}
_REMINDER_KIND_LABELS = {"task": "Task", "event": "Event", "shopping": "Shopping list"}


async def _describe_reminder(item: dict) -> None:
    """Resolve a `reminder:{kind}:{entity_id}:{date}` dedup marker to a readable label."""
    parts = item["key"].split(":", 3)
    if len(parts) != 4:
        return
    _, kind, entity_id, reminded_date = parts
    label = _REMINDER_KIND_LABELS.get(kind, kind.title())

    if kind == "shopping":
        item["display_text"] = f"{label}: pending items reminder"
    else:
        title = f"#{entity_id}"
        path = _REMINDER_KIND_PATHS.get(kind)
        if path:
            try:
                entity = await api.get(f"{path}/{entity_id}")
                title = entity.get("title", title)
            except httpx.HTTPError:
                title = f"#{entity_id} (deleted)"
        item["display_text"] = f"{label}: {title}"
    item["display_meta"] = f"reminded {reminded_date}"


async def _resolve_working_memory(items: list[dict]) -> list[dict]:
    for item in items:
        if item["key"].startswith("reminder:"):
            await _describe_reminder(item)
    return items


@router.delete("/memories/{memory_id}", response_class=HTMLResponse)
async def delete_memory(memory_id: int):
    try:
        await api.delete(f"/core/memories/{memory_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete memory.</p>', status_code=422)
    return HTMLResponse("")


@router.delete("/working-memory/{item_id}", response_class=HTMLResponse)
async def delete_working_memory(item_id: int):
    try:
        await api.delete(f"/core/working-memory/{item_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete entry.</p>', status_code=422)
    return HTMLResponse("")


@router.get("/", response_class=HTMLResponse)
async def insights_page(request: Request):
    memories_raw, working_memories_raw, llm_calls, provider_calls, cmd_executions, embedding_calls = [], [], [], [], [], []
    messages, sessions = [], []

    for path, params, target in [
        ("/core/memories", {"limit": 200}, "memories"),
        ("/core/working-memory", {"expired": "active", "limit": 200}, "working_memories"),
        ("/integration/llm-calls", {"limit": 200}, "llm_calls"),
        ("/integration/provider-calls", {"limit": 200}, "provider_calls"),
        ("/core/command-executions", {"limit": 200}, "cmd_executions"),
        ("/integration/embedding-calls", {"limit": 200}, "embedding_calls"),
        ("/core/messages", {"skip": 0, "limit": 200}, "messages"),
        ("/core/sessions", {"skip": 0, "limit": 200}, "sessions"),
    ]:
        try:
            result = await api.get(path, params=params)
            if target == "memories":          memories_raw = result
            elif target == "working_memories": working_memories_raw = result
            elif target == "llm_calls":       llm_calls = result
            elif target == "provider_calls":  provider_calls = result
            elif target == "cmd_executions":  cmd_executions = result
            elif target == "embedding_calls": embedding_calls = result
            elif target == "messages":        messages = result
            elif target == "sessions":        sessions = result
        except httpx.HTTPError:
            pass

    # ── LLM aggregations ─────────────────────────────────────────
    llm_by_model = dict(Counter(c["model"] for c in llm_calls).most_common())
    llm_by_feature = dict(Counter(c["feature"] for c in llm_calls).most_common(10))
    tokens_by_feature: dict[str, int] = defaultdict(int)
    for c in llm_calls:
        tokens_by_feature[c["feature"]] += (c.get("tokens_input") or 0) + (c.get("tokens_output") or 0)
    tokens_by_feature = dict(sorted(tokens_by_feature.items(), key=lambda kv: -kv[1])[:10])
    total_tokens_in = sum(c.get("tokens_input") or 0 for c in llm_calls)
    total_tokens_out = sum(c.get("tokens_output") or 0 for c in llm_calls)
    avg_latency = (
        sum(c.get("latency_ms") or 0 for c in llm_calls) / len(llm_calls)
        if llm_calls else 0
    )

    # ── Provider call aggregations ────────────────────────────────
    provider_by_name = dict(Counter(c["provider"] for c in provider_calls).most_common())
    provider_by_status = dict(Counter(c["status"] for c in provider_calls).most_common())

    # ── Command execution aggregations ────────────────────────────
    cmd_by_name = dict(Counter(c["command_name"] for c in cmd_executions).most_common(10))
    cmd_by_status = dict(Counter(c["status"] for c in cmd_executions).most_common())

    # ── Embedding call aggregations ───────────────────────────────
    embedding_calls_by_feature = dict(Counter(c["feature"] for c in embedding_calls).most_common(10))

    # ── Messages/sessions aggregations ────────────────────────────
    messages_by_role = dict(Counter(m["role"] for m in messages).most_common())
    sessions_by_source = dict(Counter(s["source"] or "unknown" for s in sessions).most_common())

    # ── Previews ────────────────────────────────────────────────
    wm_preview = await _resolve_working_memory(working_memories_raw[:_PREVIEW_SIZE])
    memories_preview = memories_raw[:_PREVIEW_SIZE]

    return templates.TemplateResponse(request, "insights.html", {
        # memories (preview)
        "memories_preview": memories_preview,
        "total_memories": len(memories_raw),
        # working memory (preview)
        "wm_preview": wm_preview,
        "total_wm": len(working_memories_raw),
        # llm
        "llm_calls": llm_calls[:_LLM_CALLS_PREVIEW_SIZE],
        "provider_calls": provider_calls[:_PROVIDER_CALLS_PREVIEW_SIZE],
        "total_llm_calls": len(llm_calls),
        "total_tokens": total_tokens_in + total_tokens_out,
        "total_provider_calls": len(provider_calls),
        "avg_latency_ms": round(avg_latency),
        # embedding calls
        "embedding_calls": embedding_calls[:_EMBEDDING_CALLS_PREVIEW_SIZE],
        "total_embedding_calls": len(embedding_calls),
        # messages/sessions (preview)
        "messages_preview": messages[:_MESSAGES_PREVIEW_SIZE],
        "total_messages": len(messages),
        "sessions_preview": sessions[:_SESSIONS_PREVIEW_SIZE],
        "total_sessions": len(sessions),
        # chart data
        "llm_by_model": llm_by_model,
        "llm_by_feature": llm_by_feature,
        "tokens_by_feature": tokens_by_feature,
        "provider_by_name": provider_by_name,
        "provider_by_status": provider_by_status,
        "cmd_by_name": cmd_by_name,
        "cmd_by_status": cmd_by_status,
        "embedding_calls_by_feature": embedding_calls_by_feature,
        "messages_by_role": messages_by_role,
        "sessions_by_source": sessions_by_source,
    })


async def _wm_key_prefix_options() -> list[str]:
    """Distinct key prefixes ("types") for the filter dropdown, from a recent sample."""
    try:
        raw = await api.get(
            "/core/working-memory", params={"limit": _FILTER_OPTIONS_SAMPLE_LIMIT, "expired": "all"}
        )
    except httpx.HTTPError:
        raw = []
    return sorted({w["key"].split(":")[0] for w in raw if ":" in w["key"]})


@router.get("/working-memory", response_class=HTMLResponse)
async def working_memory_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    key_contains = request.query_params.get("key_contains", "").strip()
    key_prefix = request.query_params.get("type", "").strip()
    expired = request.query_params.get("expired", "active").strip() or "active"

    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset, "expired": expired}
    if key_contains:
        params["key_contains"] = key_contains
    if key_prefix:
        params["key_prefix"] = key_prefix

    try:
        raw = await api.get("/core/working-memory", params=params)
    except httpx.HTTPError:
        raw = []

    items, has_next, has_prev = _pagination(raw, offset)
    items = await _resolve_working_memory(items)
    key_prefix_options = await _wm_key_prefix_options()
    filter_qs = urlencode({
        k: v for k, v in {"key_contains": key_contains, "type": key_prefix, "expired": expired}.items() if v
    })

    return templates.TemplateResponse(request, "working_memory.html", {
        "items": items,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "key_contains": key_contains,
        "key_prefix": key_prefix,
        "expired": expired,
        "key_prefix_options": key_prefix_options,
        "filter_qs": filter_qs,
    })


async def _memory_category_options() -> list[str]:
    """Distinct categories for the filter dropdown, from a recent sample."""
    try:
        raw = await api.get("/core/memories", params={"limit": _FILTER_OPTIONS_SAMPLE_LIMIT})
    except httpx.HTTPError:
        raw = []
    return sorted({m["category"] for m in raw})


@router.get("/memories", response_class=HTMLResponse)
async def memories_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    category = request.query_params.get("category", "").strip()
    q = request.query_params.get("q", "").strip()
    sort = request.query_params.get("sort", "importance").strip() or "importance"

    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset, "sort": sort}
    if category:
        params["category"] = category
    if q:
        params["q"] = q

    try:
        raw = await api.get("/core/memories", params=params)
    except httpx.HTTPError:
        raw = []

    items, has_next, has_prev = _pagination(raw, offset)
    categories = await _memory_category_options()
    filter_qs = urlencode({k: v for k, v in {"category": category, "q": q, "sort": sort}.items() if v})

    return templates.TemplateResponse(request, "memories.html", {
        "items": items,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "category": category,
        "q": q,
        "sort": sort,
        "categories": categories,
        "filter_qs": filter_qs,
    })


async def _llm_call_filter_options() -> tuple[list[str], list[str]]:
    """Distinct models/features for the filter dropdowns, from a recent sample of calls."""
    try:
        raw = await api.get("/integration/llm-calls", params={"limit": _LLM_CALL_OPTIONS_LIMIT})
    except httpx.HTTPError:
        raw = []
    models = sorted({c["model"] for c in raw})
    features = sorted({c["feature"] for c in raw})
    return models, features


@router.get("/llm-calls", response_class=HTMLResponse)
async def llm_calls_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    model = request.query_params.get("model", "").strip()
    feature = request.query_params.get("feature", "").strip()
    q = request.query_params.get("q", "").strip()

    params: dict = {"limit": _PAGE_SIZE + 1, "skip": offset}
    if model:
        params["model"] = model
    if feature:
        params["feature"] = feature
    if q:
        params["q"] = q

    try:
        raw = await api.get("/integration/llm-calls", params=params)
    except httpx.HTTPError:
        raw = []

    calls, has_next, has_prev = _pagination(raw, offset)
    models, features = await _llm_call_filter_options()
    filter_qs = urlencode({k: v for k, v in {"model": model, "feature": feature, "q": q}.items() if v})

    return templates.TemplateResponse(request, "llm_calls.html", {
        "calls": calls,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "model": model,
        "feature": feature,
        "q": q,
        "models": models,
        "features": features,
        "filter_qs": filter_qs,
    })


async def _provider_call_filter_options() -> tuple[list[str], list[str], list[str], list[str]]:
    """Distinct providers/operations/entity types/statuses for the filter dropdowns, from a recent sample."""
    try:
        raw = await api.get("/integration/provider-calls", params={"limit": _PROVIDER_CALL_OPTIONS_LIMIT})
    except httpx.HTTPError:
        raw = []
    providers = sorted({c["provider"] for c in raw})
    operations = sorted({c["operation"] for c in raw})
    entity_types = sorted({c["entity_type"] for c in raw})
    statuses = sorted({c["status"] for c in raw})
    return providers, operations, entity_types, statuses


@router.get("/provider-calls", response_class=HTMLResponse)
async def provider_calls_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    provider = request.query_params.get("provider", "").strip()
    operation = request.query_params.get("operation", "").strip()
    entity_type = request.query_params.get("entity_type", "").strip()
    status = request.query_params.get("status", "").strip()
    q = request.query_params.get("q", "").strip()

    params: dict = {"limit": _PAGE_SIZE + 1, "skip": offset}
    if provider:
        params["provider"] = provider
    if operation:
        params["operation"] = operation
    if entity_type:
        params["entity_type"] = entity_type
    if status:
        params["status"] = status
    if q:
        params["q"] = q

    try:
        raw = await api.get("/integration/provider-calls", params=params)
    except httpx.HTTPError:
        raw = []

    calls, has_next, has_prev = _pagination(raw, offset)
    providers, operations, entity_types, statuses = await _provider_call_filter_options()
    filter_qs = urlencode({
        k: v for k, v in {
            "provider": provider, "operation": operation, "entity_type": entity_type, "status": status, "q": q,
        }.items() if v
    })

    return templates.TemplateResponse(request, "provider_calls.html", {
        "calls": calls,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "provider": provider,
        "operation": operation,
        "entity_type": entity_type,
        "status": status,
        "q": q,
        "providers": providers,
        "operations": operations,
        "entity_types": entity_types,
        "statuses": statuses,
        "filter_qs": filter_qs,
    })


@router.get("/llm-calls/{call_id}/detail", response_class=HTMLResponse)
async def llm_call_detail(call_id: int, request: Request):
    try:
        call = await api.get(f"/integration/llm-calls/{call_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to load call.</p>', status_code=422)
    return templates.TemplateResponse(request, "_llm_call_detail.html", {"call": call})


@router.get("/provider-calls/{call_id}/detail", response_class=HTMLResponse)
async def provider_call_detail(call_id: int, request: Request):
    try:
        call = await api.get(f"/integration/provider-calls/{call_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to load call.</p>', status_code=422)
    return templates.TemplateResponse(request, "_provider_call_detail.html", {"call": call})


async def _embedding_call_filter_options() -> list[str]:
    """Distinct features for the filter dropdown, from a recent sample of calls."""
    try:
        raw = await api.get("/integration/embedding-calls", params={"limit": _EMBEDDING_CALL_OPTIONS_LIMIT})
    except httpx.HTTPError:
        raw = []
    return sorted({c["feature"] for c in raw})


@router.get("/embedding-calls", response_class=HTMLResponse)
async def embedding_calls_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    feature = request.query_params.get("feature", "").strip()
    q = request.query_params.get("q", "").strip()

    params: dict = {"limit": _PAGE_SIZE + 1, "skip": offset}
    if feature:
        params["feature"] = feature
    if q:
        params["q"] = q

    try:
        raw = await api.get("/integration/embedding-calls", params=params)
    except httpx.HTTPError:
        raw = []

    calls, has_next, has_prev = _pagination(raw, offset)
    features = await _embedding_call_filter_options()
    filter_qs = urlencode({k: v for k, v in {"feature": feature, "q": q}.items() if v})

    return templates.TemplateResponse(request, "embedding_calls.html", {
        "calls": calls,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "feature": feature,
        "q": q,
        "features": features,
        "filter_qs": filter_qs,
    })


@router.get("/embedding-calls/{call_id}/detail", response_class=HTMLResponse)
async def embedding_call_detail(call_id: int, request: Request):
    try:
        call = await api.get(f"/integration/embedding-calls/{call_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to load call.</p>', status_code=422)
    return templates.TemplateResponse(request, "_embedding_call_detail.html", {"call": call})


async def _embedding_source_type_options() -> list[str]:
    """Distinct source types for the filter dropdown, from a recent sample of embeddings."""
    try:
        raw = await api.get("/core/embeddings", params={"limit": _FILTER_OPTIONS_SAMPLE_LIMIT})
    except httpx.HTTPError:
        raw = []
    return sorted({e["source_type"] for e in raw})


@router.delete("/embeddings/{embedding_id}", response_class=HTMLResponse)
async def delete_embedding(embedding_id: int):
    try:
        await api.delete(f"/core/embeddings/{embedding_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete embedding.</p>', status_code=422)
    return HTMLResponse("")


@router.get("/embeddings", response_class=HTMLResponse)
async def embeddings_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    source_type = request.query_params.get("source_type", "").strip()
    q = request.query_params.get("q", "").strip()

    params: dict = {"limit": _PAGE_SIZE + 1, "skip": offset}
    if source_type:
        params["source_type"] = source_type
    if q:
        params["q"] = q

    try:
        raw = await api.get("/core/embeddings", params=params)
    except httpx.HTTPError:
        raw = []

    items, has_next, has_prev = _pagination(raw, offset)
    source_types = await _embedding_source_type_options()
    filter_qs = urlencode({k: v for k, v in {"source_type": source_type, "q": q}.items() if v})

    return templates.TemplateResponse(request, "embeddings.html", {
        "items": items,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "source_type": source_type,
        "q": q,
        "source_types": source_types,
        "filter_qs": filter_qs,
    })


@router.get("/messages", response_class=HTMLResponse)
async def messages_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    role = request.query_params.get("role", "").strip()
    source = request.query_params.get("source", "").strip()
    q = request.query_params.get("q", "").strip()
    session_id = request.query_params.get("session_id", "").strip()

    params: dict = {"skip": offset, "limit": _PAGE_SIZE + 1}
    if role:
        params["role"] = role
    if source:
        params["source"] = source
    if q:
        params["q"] = q
    if session_id:
        params["session_id"] = session_id

    try:
        raw = await api.get("/core/messages", params=params)
    except httpx.HTTPError:
        raw = []

    items, has_next, has_prev = _pagination(raw, offset)
    filter_qs = urlencode(
        {k: v for k, v in {"role": role, "source": source, "q": q, "session_id": session_id}.items() if v}
    )

    return templates.TemplateResponse(request, "messages.html", {
        "items": items,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "role": role,
        "source": source,
        "q": q,
        "session_id": session_id,
        "roles": _MESSAGE_ROLES,
        "sources": _MESSAGE_SOURCES,
        "filter_qs": filter_qs,
    })


@router.get("/messages/{message_id}/detail", response_class=HTMLResponse)
async def message_detail(message_id: int, request: Request):
    try:
        message = await api.get(f"/core/messages/{message_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to load message.</p>', status_code=422)
    return templates.TemplateResponse(request, "_message_detail.html", {"message": message})


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    source = request.query_params.get("source", "").strip()
    active_only = request.query_params.get("active_only", "").strip() == "true"
    q = request.query_params.get("q", "").strip()

    params: dict = {"skip": offset, "limit": _PAGE_SIZE + 1}
    if source:
        params["source"] = source
    if active_only:
        params["active_only"] = True
    if q:
        params["q"] = q

    try:
        raw = await api.get("/core/sessions", params=params)
    except httpx.HTTPError:
        raw = []

    items, has_next, has_prev = _pagination(raw, offset)
    filter_qs = urlencode({
        k: v for k, v in {"source": source, "active_only": "true" if active_only else "", "q": q}.items() if v
    })

    return templates.TemplateResponse(request, "sessions.html", {
        "items": items,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "source": source,
        "active_only": active_only,
        "q": q,
        "sources": _SESSION_SOURCES,
        "filter_qs": filter_qs,
    })


@router.get("/sessions/{session_id}/detail", response_class=HTMLResponse)
async def session_detail(session_id: int, request: Request):
    try:
        session_obj = await api.get(f"/core/sessions/{session_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to load session.</p>', status_code=422)
    return templates.TemplateResponse(request, "_session_detail.html", {"session": session_obj})
