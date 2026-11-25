import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.shared.forward import safe_get
from app.shared.settings_page import build_sections, read_paths, unregistered_preview
from app.templates_config import templates

router = APIRouter(prefix="/settings")

_CATALOG_PATH = "/core/settings/catalog"


@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request):
    catalog = await safe_get(_CATALOG_PATH)
    if catalog is None:
        return templates.TemplateResponse(request, "settings.html", {"sections": None})
    paths = read_paths(catalog)
    values = await asyncio.gather(*(safe_get(path) for path in paths))
    unregistered, unregistered_total = unregistered_preview(catalog)
    return templates.TemplateResponse(request, "settings.html", {
        "sections": build_sections(catalog, dict(zip(paths, values))),
        "unregistered": unregistered,
        "unregistered_total": unregistered_total,
    })


@router.get("/stored", response_class=HTMLResponse)
async def stored_settings_page(request: Request):
    catalog = await safe_get(_CATALOG_PATH)
    return templates.TemplateResponse(request, "settings_stored.html", {
        "rows": catalog["unregistered"] if catalog else None,
    })
