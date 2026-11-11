import csv
import io
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

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


def _link_kind(kind: str) -> str:
    """Only the three linkable kinds reach the backend path."""
    if kind not in ("legs", "stays", "visits"):
        raise HTTPException(status_code=404)
    return kind


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
        "city": (params.get("city") or "").strip(),
        "country": (params.get("country") or "").strip(),
    }


def _list_context(request: Request, trips: list | None, offset: int, filters: dict) -> dict:
    page, has_next, has_prev = _pagination(trips or [], offset)
    query = [("status", filters["status"]), ("q", filters["q"]), ("date_from", filters["date_from"]),
             ("date_to", filters["date_to"]), ("city", filters["city"]), ("country", filters["country"]),
             *[("tag", t) for t in filters["tags"]]]
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
    for key in ("q", "date_from", "date_to", "city", "country"):
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


@router.get("/transactions/search")
async def search_transactions(q: str = ""):
    """Finance transactions matching a free-text search, for the link dialog."""
    if not q.strip():
        return JSONResponse([])
    found = await safe_get("/finance/transactions", params={"search": q.strip(), "limit": 10})
    if found is None:
        return JSONResponse({"error": "Could not search transactions."}, status_code=502)
    return JSONResponse(found)


@router.get("/links/{kind}/{entity_id}")
async def get_links(kind: str, entity_id: int):
    return await forward(api.get(f"/travel/{_link_kind(kind)}/{entity_id}/transactions"), "Could not load the transactions.")


@router.post("/links/{kind}/{entity_id}")
async def create_link(kind: str, entity_id: int, request: Request):
    return await forward(
        api.post(f"/travel/{_link_kind(kind)}/{entity_id}/transactions", json=await request.json()),
        "Could not link the transaction.",
    )


@router.delete("/links/{kind}/{entity_id}/{transaction_id}")
async def delete_link(kind: str, entity_id: int, transaction_id: int):
    return await forward(
        api.delete(f"/travel/{_link_kind(kind)}/{entity_id}/transactions/{transaction_id}"),
        "Could not unlink the transaction.",
    )


@router.post("/trips/{trip_id}/apply-default-tags")
async def apply_default_tags(trip_id: int):
    return await forward(api.post(f"/travel/trips/{trip_id}/apply-default-tags"), "Could not tag the expenses.")


@router.get("/trips/{trip_id}/calendar-events")
async def calendar_events(trip_id: int):
    return await forward(api.get(f"/travel/trips/{trip_id}/calendar-events"), "Could not read the calendar.")


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


def _place_filters(request: Request) -> dict:
    params = request.query_params
    status = params.get("status") or ""
    return {
        "q": (params.get("q") or "").strip(),
        "kind": params.get("kind") if params.get("kind") in _PLACE_KINDS else "",
        "city": (params.get("city") or "").strip(),
        "country": (params.get("country") or "").strip(),
        "tags": [t for t in params.getlist("tag") if t],
        "min_grade": params.get("min_grade") if params.get("min_grade") in ("1", "2", "3", "4", "5") else "",
        "status": status if status in ("planned", "visited", "missed") else "",
        "no_trip": params.get("no_trip") in ("1", "true", "on"),
        "ungraded": params.get("ungraded") in ("1", "true", "on"),
    }


def _places_context(places: list | None, offset: int, filters: dict) -> dict:
    page, has_next, has_prev = _pagination(places or [], offset)
    query = [(k, filters[k]) for k in ("q", "kind", "city", "country", "min_grade", "status")]
    query += [("tag", t) for t in filters["tags"]]
    if filters["no_trip"]:
        query.append(("no_trip", "1"))
    if filters["ungraded"]:
        query.append(("ungraded", "1"))
    return {
        "places": page, "available": places is not None, "offset": offset, "has_next": has_next,
        "has_prev": has_prev, "page_size": _PAGE_SIZE, "query": urlencode([(k, v) for k, v in query if v]),
    }


async def _fetch_places(filters: dict, offset: int) -> list | None:
    params: list[tuple[str, object]] = [("limit", _PAGE_SIZE + 1), ("offset", offset)]
    for key in ("q", "kind", "city", "country", "min_grade", "status"):
        if filters[key]:
            params.append((key, filters[key]))
    params += [("tag", t) for t in filters["tags"]]
    if filters["no_trip"]:
        params.append(("no_trip", "true"))
    if filters["ungraded"]:
        params.append(("ungraded", "true"))
    return await safe_get("/travel/places", params=params)


# "/places..." is registered before "/{trip_id}" so it is never read as a trip id.

@router.get("/places", response_class=HTMLResponse)
async def places_page(request: Request):
    filters = _place_filters(request)
    places = await _fetch_places(filters, 0)
    tags = await safe_get("/travel/tags", default=[])
    return templates.TemplateResponse(request, "travel_places.html", {
        **_places_context(places, 0, filters), "filters": filters, "place_kinds": _PLACE_KINDS,
        "all_tags": [t["name"] for t in tags or []],
    })


@router.get("/places/list", response_class=HTMLResponse)
async def places_list(request: Request):
    filters = _place_filters(request)
    offset = _int_param(request.query_params.get("offset"))
    places = await _fetch_places(filters, offset)
    return templates.TemplateResponse(request, "_travel_places_list.html", _places_context(places, offset, filters))


@router.patch("/places/{place_id}")
async def update_place(place_id: int, request: Request):
    return await forward(api.patch(f"/travel/places/{place_id}", json=await request.json()), "Could not update the place.")


@router.delete("/places/{place_id}")
async def delete_place(place_id: int):
    return await forward(api.delete(f"/travel/places/{place_id}"), "Could not delete the place.")


@router.post("/visits")
async def create_visit(request: Request):
    return await forward(api.post("/travel/visits", json=await request.json()), "Could not add the visit.")


@router.patch("/visits/{visit_id}")
async def update_visit(visit_id: int, request: Request):
    return await forward(api.patch(f"/travel/visits/{visit_id}", json=await request.json()), "Could not update the visit.")


@router.delete("/visits/{visit_id}")
async def delete_visit(visit_id: int):
    return await forward(api.delete(f"/travel/visits/{visit_id}"), "Could not delete the visit.")


@router.get("/places/{place_id}", response_class=HTMLResponse)
async def place_page(place_id: int, request: Request):
    place = await safe_get(f"/travel/places/{place_id}")
    if place is None:
        return RedirectResponse("/travel/places", status_code=302)
    costs = await safe_get(f"/travel/places/{place_id}/costs")
    return templates.TemplateResponse(request, "travel_place.html", {
        "place": place, "place_kinds": _PLACE_KINDS, "place_cost": costs["total"] if costs else None,
    })


@router.get("/{trip_id}/map.csv")
async def trip_map_csv(trip_id: int, scope: str = "all"):
    """The trip's pins as a CSV that Google My Maps imports (it geocodes the Address column).

    scope=planned/visited/missed keeps only pins with that status; anything else means all.
    """
    scope = scope if scope in ("planned", "visited", "missed") else "all"
    data = await safe_get(f"/travel/trips/{trip_id}/map", params={"scope": scope})
    if data is None:
        return RedirectResponse(f"/travel/{trip_id}", status_code=302)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Name", "Address", "Category", "Status", "Description"])
    for point in data["points"]:
        writer.writerow([point["name"], point["address"], point["category"], point["status"], point["description"] or ""])
    filename = f"trip-{trip_id}-map{'' if scope == 'all' else '-' + scope}.csv"
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{trip_id}/recap", response_class=HTMLResponse)
async def recap_page(trip_id: int, request: Request):
    recap = await safe_get(f"/travel/trips/{trip_id}/recap")
    if recap is None:
        return RedirectResponse(f"/travel/{trip_id}", status_code=302)
    return templates.TemplateResponse(request, "travel_recap.html", {"recap": recap})


@router.get("/{trip_id}", response_class=HTMLResponse)
async def trip_page(trip_id: int, request: Request):
    all_visits = request.query_params.get("all_visits") in ("1", "true")
    trip = await safe_get(f"/travel/trips/{trip_id}", params={"all_visits": "true"} if all_visits else None)
    if trip is None:
        return RedirectResponse("/travel", status_code=302)
    places = await safe_get("/travel/places", params={"limit": 500}, default=[])
    days: dict[str, list] = {}
    for item in trip["timeline"]:
        days.setdefault(item["local"][:10], []).append(item)
    costs = await safe_get(f"/travel/trips/{trip_id}/costs")
    entity_costs = {
        kind: {item["id"]: item for item in (costs or {}).get(kind, [])} for kind in ("legs", "stays", "visits")
    }
    visit_days: dict[str | None, list] = {}
    for visit in trip["visits"]:
        visit_days.setdefault(visit["visit_date"], []).append(visit)
    return templates.TemplateResponse(request, "travel_trip.html", {
        "trip": trip,
        "days": days,
        "visit_days": visit_days,
        "costs": costs,
        "entity_costs": entity_costs,
        "all_visits": all_visits,
        "places": places,
        "place_kinds": _PLACE_KINDS,
        "leg_modes": _LEG_MODES,
        "zones": _ZONES,
        "default_zone": get_settings().timezone,
    })
