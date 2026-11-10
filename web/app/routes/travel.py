from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.client as api
from app.config import get_settings
from app.shared.forward import forward, safe_get
from app.templates_config import templates

router = APIRouter(prefix="/travel")

_PAGE_SIZE = 20
_STATUSES = {"current": "Upcoming & ongoing", "upcoming": "Upcoming", "ongoing": "Ongoing", "past": "Past", "all": "All"}
_PLACE_KINDS = ["hotel", "restaurant", "cafe", "activity", "museum", "attraction", "shop", "other"]
_LEG_MODES = ["flight", "train", "bus", "ferry", "car", "other"]
# Suggestions for the time zone fields; any IANA name can still be typed.
_ZONES = [
    "Europe/Lisbon", "Europe/London", "Europe/Madrid", "Europe/Paris", "Europe/Berlin", "Europe/Rome",
    "Europe/Stockholm", "Europe/Helsinki", "Europe/Athens", "Europe/Istanbul", "America/New_York",
    "America/Sao_Paulo", "America/Argentina/Buenos_Aires", "Asia/Dubai", "Asia/Tokyo", "UTC",
]


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _PAGE_SIZE
    return items[:_PAGE_SIZE], has_next, offset > 0


def _int_param(raw: str | None, default: int = 0) -> int:
    try:
        return max(0, int(raw)) if raw not in (None, "") else default
    except ValueError:
        return default


def _filters(request: Request) -> dict:
    params = request.query_params
    status = params.get("status", "current")
    return {
        "status": status if status in _STATUSES else "current",
        "tags": [t for t in params.getlist("tag") if t],
        "q": (params.get("q") or "").strip(),
        "date_from": params.get("date_from") or "",
        "date_to": params.get("date_to") or "",
    }


def _list_context(request: Request, trips: list | None, offset: int, filters: dict) -> dict:
    page, has_next, has_prev = _pagination(trips or [], offset)
    query = [("status", filters["status"]), ("q", filters["q"]), ("date_from", filters["date_from"]),
             ("date_to", filters["date_to"]), *[("tag", t) for t in filters["tags"]]]
    return {
        "trips": page,
        "available": trips is not None,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "page_size": _PAGE_SIZE,
        "query": urlencode([(k, v) for k, v in query if v]),
    }


async def _fetch_trips(filters: dict, offset: int) -> list | None:
    params: list[tuple[str, object]] = [("status", filters["status"]), ("limit", _PAGE_SIZE + 1), ("offset", offset)]
    params += [("tag", t) for t in filters["tags"]]
    for key in ("q", "date_from", "date_to"):
        if filters[key]:
            params.append((key, filters[key]))
    return await safe_get("/travel/trips", params=params)


@router.get("", response_class=HTMLResponse)
async def trips_page(request: Request):
    filters = _filters(request)
    trips = await _fetch_trips(filters, 0)
    tags = await safe_get("/travel/tags", default=[])
    settings = await safe_get("/travel/settings")
    context = _list_context(request, trips, 0, filters)
    return templates.TemplateResponse(request, "travel.html", {
        **context, "filters": filters, "statuses": _STATUSES, "all_tags": [t["name"] for t in tags or []],
        "settings": settings,
    })


@router.get("/list", response_class=HTMLResponse)
async def trips_list(request: Request):
    filters = _filters(request)
    offset = _int_param(request.query_params.get("offset"))
    trips = await _fetch_trips(filters, offset)
    return templates.TemplateResponse(request, "_travel_trips_list.html", _list_context(request, trips, offset, filters))


# Writes proxy to the backend and relay its error message. Static paths come before "/{trip_id}".

@router.put("/settings")
async def update_settings(request: Request):
    return await forward(api.put("/travel/settings", json=await request.json()), "Could not save the settings.")


@router.post("/trips")
async def create_trip(request: Request):
    return await forward(api.post("/travel/trips", json=await request.json()), "Could not create the trip.")


@router.patch("/trips/{trip_id}")
async def update_trip(trip_id: int, request: Request):
    return await forward(api.patch(f"/travel/trips/{trip_id}", json=await request.json()), "Could not update the trip.")


@router.delete("/trips/{trip_id}")
async def delete_trip(trip_id: int):
    return await forward(api.delete(f"/travel/trips/{trip_id}"), "Could not delete the trip.")


@router.post("/legs")
async def create_leg(request: Request):
    return await forward(api.post("/travel/legs", json=await request.json()), "Could not add the leg.")


@router.patch("/legs/{leg_id}")
async def update_leg(leg_id: int, request: Request):
    return await forward(api.patch(f"/travel/legs/{leg_id}", json=await request.json()), "Could not update the leg.")


@router.delete("/legs/{leg_id}")
async def delete_leg(leg_id: int):
    return await forward(api.delete(f"/travel/legs/{leg_id}"), "Could not delete the leg.")


@router.post("/stays")
async def create_stay(request: Request):
    return await forward(api.post("/travel/stays", json=await request.json()), "Could not add the stay.")


@router.patch("/stays/{stay_id}")
async def update_stay(stay_id: int, request: Request):
    return await forward(api.patch(f"/travel/stays/{stay_id}", json=await request.json()), "Could not update the stay.")


@router.delete("/stays/{stay_id}")
async def delete_stay(stay_id: int):
    return await forward(api.delete(f"/travel/stays/{stay_id}"), "Could not delete the stay.")


@router.post("/places")
async def create_place(request: Request):
    return await forward(api.post("/travel/places", json=await request.json()), "Could not create the place.")


@router.get("/{trip_id}", response_class=HTMLResponse)
async def trip_page(trip_id: int, request: Request):
    trip = await safe_get(f"/travel/trips/{trip_id}")
    if trip is None:
        return RedirectResponse("/travel", status_code=302)
    places = await safe_get("/travel/places", params={"limit": 500}, default=[])
    days: dict[str, list] = {}
    for item in trip["timeline"]:
        days.setdefault(item["local"][:10], []).append(item)
    return templates.TemplateResponse(request, "travel_trip.html", {
        "trip": trip,
        "days": days,
        "places": places,
        "place_kinds": _PLACE_KINDS,
        "leg_modes": _LEG_MODES,
        "zones": _ZONES,
        "default_zone": get_settings().timezone,
    })
