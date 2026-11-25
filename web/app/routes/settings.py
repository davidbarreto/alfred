import asyncio
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import app.client as api
from app.shared.forward import error_detail, safe_get
from app.shared.settings_page import (
    SaveError,
    build_sections,
    plan_writes,
    read_paths,
    saved_values,
    section_notes,
    unregistered_preview,
)
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings")

_CATALOG_PATH = "/core/settings/catalog"


@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request):
    catalog = await safe_get(_CATALOG_PATH)
    if catalog is None:
        return templates.TemplateResponse(request, "settings.html", {"sections": None})
    paths = read_paths(catalog)
    *values, current_period = await asyncio.gather(
        *(safe_get(path) for path in paths), safe_get("/finance/budgets/current-period")
    )
    unregistered, unregistered_total = unregistered_preview(catalog)
    return templates.TemplateResponse(request, "settings.html", {
        "sections": build_sections(catalog, dict(zip(paths, values)), section_notes(current_period)),
        "unregistered": unregistered,
        "unregistered_total": unregistered_total,
    })


@router.get("/stored", response_class=HTMLResponse)
async def stored_settings_page(request: Request):
    catalog = await safe_get(_CATALOG_PATH)
    return templates.TemplateResponse(request, "settings_stored.html", {
        "rows": catalog["unregistered"] if catalog else None,
    })


async def _save_namespace(catalog: dict, namespace: str, writes: list[tuple[str, dict]]) -> dict:
    """One namespace's PUTs in order; the first failure stops it and its message is relayed."""
    responses = []
    for path, body in writes:
        try:
            responses.append(await api.put(path, json=body))
        except httpx.HTTPStatusError as exc:
            return {"ok": False, "error": error_detail(exc, "Could not save these settings.")}
        except httpx.HTTPError:
            return {"ok": False, "error": "Could not reach the backend."}
    return {"ok": True, "values": saved_values(catalog, namespace, responses)}


@router.post("/save")
async def save_settings(request: Request):
    """Body: {namespace: {field: value}} with only the changed fields. Answers per namespace, never all-or-nothing."""
    changes = await request.json()
    if not isinstance(changes, dict) or not all(isinstance(v, dict) for v in changes.values()):
        return JSONResponse({"error": "Expected {namespace: {field: value}}."}, status_code=422)
    catalog = await safe_get(_CATALOG_PATH)
    if catalog is None:
        return JSONResponse({"error": "Could not load the settings catalog."}, status_code=502)
    try:
        plan = plan_writes(catalog, changes)
    except SaveError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    namespaces = list(plan)
    results = await asyncio.gather(*(_save_namespace(catalog, ns, plan[ns]) for ns in namespaces))
    logger.info(
        "Settings saved: namespaces=%s failed=%s",
        namespaces, [ns for ns, result in zip(namespaces, results) if not result["ok"]],
    )
    return JSONResponse(dict(zip(namespaces, results)))
