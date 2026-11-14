import csv
import io
from datetime import date, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import app.client as api
from app.config import get_settings
from app.shared.forward import forward, safe_get
from app.shared.timezone import local_today
from app.templates_config import templates

router = APIRouter(prefix="/travel")

_PAGE_SIZE = 20
# The trip page shows this many timeline steps; the rest are on /travel/{id}/timeline.
_TIMELINE_PREVIEW = 8
_STATUSES = {"current": "Upcoming & ongoing", "upcoming": "Upcoming", "ongoing": "Ongoing", "past": "Past", "all": "All"}
_WARNING_PREVIEW = 5
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
    checklist = await safe_get("/travel/checklist-template", default=[])
    locations = await safe_get("/travel/trips/locations", default={"cities": [], "countries": []})
    context = _list_context(request, trips, 0, filters)
    return templates.TemplateResponse(request, "travel.html", {
        **context, "filters": filters, "statuses": _STATUSES, "all_tags": [t["name"] for t in tags or []],
        "settings": settings, "checklist": checklist or [], "locations": locations,
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


@router.put("/checklist-template/{anchor}/{name}")
async def put_checklist_item(anchor: str, name: str, request: Request):
    return await forward(
        api.put(f"/travel/checklist-template/{anchor}/{name}", json=await request.json()), "Could not save the checklist item.",
    )


@router.delete("/checklist-template/{anchor}/{name}")
async def delete_checklist_item(anchor: str, name: str):
    return await forward(api.delete(f"/travel/checklist-template/{anchor}/{name}"), "Could not delete the checklist item.")


@router.get("/transactions/{transaction_id}/detail", response_class=HTMLResponse)
async def transaction_detail(transaction_id: int, request: Request):
    """A finance transaction's details as a partial, for the modal on the unlinked charges."""
    transaction = await safe_get(f"/finance/transactions/{transaction_id}")
    if transaction is None:
        return HTMLResponse('<p class="text-sm text-red-600">Could not load the transaction.</p>', status_code=502)
    accounts = await safe_get("/finance/accounts", default=[])
    categories = await safe_get("/finance/categories", default=[])
    return templates.TemplateResponse(request, "_travel_tx_detail.html", {
        "t": transaction,
        "account": next((a["name"] for a in accounts or [] if a["id"] == transaction["account_id"]), None),
        "category": next((c["name"] for c in categories or [] if c["id"] == transaction.get("category_id")), None),
    })


@router.post("/trips/{trip_id}/checklist")
async def generate_checklist(trip_id: int):
    return await forward(api.post(f"/travel/trips/{trip_id}/checklist"), "Could not create the checklist tasks.")


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


@router.post("/trips/{trip_id}/visits/move")
async def move_visits(trip_id: int, request: Request):
    return await forward(
        api.post(f"/travel/trips/{trip_id}/visits/move", json=await request.json()), "Could not move the visits.",
    )


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
    locations = await safe_get("/travel/places/locations", default={"cities": [], "countries": []})
    return templates.TemplateResponse(request, "travel_places.html", {
        **_places_context(places, 0, filters), "filters": filters, "place_kinds": _PLACE_KINDS,
        "all_tags": [t["name"] for t in tags or []], "locations": locations,
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
async def delete_visit(visit_id: int, delete_event: bool = False):
    path = f"/travel/visits/{visit_id}" + ("?delete_event=true" if delete_event else "")
    return await forward(api.delete(path), "Could not delete the visit.")


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


def _group_by_day(items: list[dict]) -> dict[str, list]:
    days: dict[str, list] = {}
    for item in items:
        days.setdefault(item["local"][:10], []).append(item)
    return days


@router.get("/{trip_id}/timeline", response_class=HTMLResponse)
async def timeline_page(trip_id: int, request: Request):
    trip = await safe_get(f"/travel/trips/{trip_id}")
    if trip is None:
        return RedirectResponse("/travel", status_code=302)
    return templates.TemplateResponse(request, "travel_timeline.html", {"trip": trip, "days": _group_by_day(trip["timeline"]), "today": local_today().isoformat()})


_PRINT_KINDS = {"leg", "arrival", "check_in", "check_out"}


def _print_days(trip: dict) -> dict[str, list[dict]]:
    """Legs, arrivals, check-ins/outs and visits as rows per local day, in time order."""
    legs = {leg["id"]: leg for leg in trip["legs"]}
    stays = {stay["id"]: stay for stay in trip["stays"]}
    rows: dict[str, list[dict]] = {}

    def add(day: str, time: str, title: str, detail: str | None = None, link: str | None = None):
        rows.setdefault(day, []).append({"time": time, "title": title, "detail": detail, "link": link})

    for item in trip["timeline"]:
        if item["kind"] not in _PRINT_KINDS:
            continue
        day, time = item["local"][:10], item["local"][11:16]
        details = []
        if item["kind"] == "leg":
            leg = legs.get(item["ref_id"], {})
            if item.get("subtitle"):
                details.append(item["subtitle"])
            if leg.get("booking_ref"):
                details.append(f"Booking {leg['booking_ref']}")
        elif item["kind"] in ("check_in", "check_out"):
            stay = stays.get(item["ref_id"], {})
            place = stay.get("place", {})
            if place.get("address"):
                details.append(place["address"])
            if stay.get("booking_ref"):
                details.append(f"Booking {stay['booking_ref']}")
        add(day, time, item["title"], " · ".join(details) or None, item.get("links", {}).get("map") if item["kind"] != "leg" else None)
    for visit in trip["visits"]:
        if visit["visit_date"]:
            time = (visit["visit_time"] or "")[:5]
            add(visit["visit_date"], time, visit["place"]["name"], visit["notes"], visit["place"]["maps_link"])
    return {day: sorted(day_rows, key=lambda r: (r["time"] == "", r["time"])) for day, day_rows in sorted(rows.items())}


@router.get("/{trip_id}/print", response_class=HTMLResponse)
async def print_page(trip_id: int, request: Request):
    trip = await safe_get(f"/travel/trips/{trip_id}", params={"all_visits": "true"})
    if trip is None:
        return RedirectResponse("/travel", status_code=302)
    visits = [v for v in trip["visits"] if v["status"] != "missed"]
    return templates.TemplateResponse(request, "travel_print.html", {"trip": {**trip, "visits": visits}, "days": _print_days({**trip, "visits": visits})})


_WARNING_LABELS = {
    "long_wait_before_check_in": "Long wait before check-in", "tight_connection": "Tight connections",
    "arrives_after_check_out": "Arrives after check-out", "overlapping_legs": "Overlapping legs",
    "uncovered_night": "Nights without a stay", "no_return_leg": "No way back",
    "visit_before_arrival": "Visits before arrival", "visit_after_departure": "Visits after departure",
    "visit_overlaps_leg": "Visits during a trip leg", "visit_without_stay": "Visits without a stay",
    "too_many_visits": "Busy days", "no_calendar_event": "Visits without a calendar event",
    "linked_event_mismatch": "Calendar event differs", "linked_event_not_updated": "Calendar event not updated", "leg_not_paid": "Legs not bought yet", "outside_trip_dates": "Outside the trip dates",
    "broken_leg_chain": "Legs that do not connect", "overlapping_stays": "Overlapping stays", "stay_not_paid": "Stays not paid yet",
    "no_booking_reference": "Missing booking references", "visits_overlap": "Visits that overlap",
    "checklist_not_generated": "Checklist not generated",
}


def _warning_groups(warnings: list[dict]) -> list[dict]:
    """Warnings grouped by kind, in order of first appearance."""
    groups: dict[str, dict] = {}
    for warning in warnings:
        kind = warning["kind"]
        group = groups.setdefault(kind, {"kind": kind, "label": _WARNING_LABELS.get(kind, kind), "items": []})
        group["items"].append(warning)
    return list(groups.values())


def _empty_days(trip: dict) -> list[str]:
    """Days of an upcoming or ongoing trip with no visit at all, as ISO dates (capped, to keep the hint short)."""
    if trip["status"] == "past":
        return []
    try:
        start, end = date.fromisoformat(trip["start_date"]), date.fromisoformat(trip["end_date"])
    except (KeyError, ValueError):
        return []
    planned = {v["visit_date"] for v in trip["visits"]}
    days = [start + timedelta(days=i) for i in range(min((end - start).days + 1, 31))]
    return [d.isoformat() for d in days if d.isoformat() not in planned]


def _countdown(minutes: int | None) -> str:
    if minutes is None:
        return ""
    hours, rest = divmod(minutes, 60)
    if hours >= 24:
        return f"in {hours // 24} d {hours % 24} h"
    return f"in {hours} h {rest:02d} min" if hours else f"in {rest} min"


@router.get("/{trip_id}/today", response_class=HTMLResponse)
async def today_page(trip_id: int, request: Request):
    today = await safe_get(f"/travel/trips/{trip_id}/today")
    if today is None:
        return RedirectResponse("/travel", status_code=302)
    return templates.TemplateResponse(request, "travel_today.html", {
        "today": today, "countdown": _countdown(today["minutes_until_next"]),
    })


@router.get("/{trip_id}/warnings", response_class=HTMLResponse)
async def warnings_page(trip_id: int, request: Request):
    trip = await safe_get(f"/travel/trips/{trip_id}")
    if trip is None:
        return RedirectResponse("/travel", status_code=302)
    other_events = await safe_get(f"/travel/trips/{trip_id}/other-events", default=[])
    return templates.TemplateResponse(request, "travel_warnings.html", {
        "trip": trip, "groups": _warning_groups(trip["warnings"]), "other_events": other_events or [],
    })


@router.get("/{trip_id}/unlinked", response_class=HTMLResponse)
async def unlinked_page(trip_id: int, request: Request):
    trip = await safe_get(f"/travel/trips/{trip_id}")
    if trip is None:
        return RedirectResponse("/travel", status_code=302)
    unlinked = await safe_get(f"/travel/trips/{trip_id}/unlinked-transactions", default=[])
    return templates.TemplateResponse(request, "travel_unlinked.html", {"trip": trip, "unlinked": unlinked or []})


@router.get("/{trip_id}/tagged", response_class=HTMLResponse)
async def tagged_page(trip_id: int, request: Request):
    trip = await safe_get(f"/travel/trips/{trip_id}")
    if trip is None:
        return RedirectResponse("/travel", status_code=302)
    tagged = await safe_get(f"/travel/trips/{trip_id}/tagged-transactions")
    return templates.TemplateResponse(request, "travel_tagged.html", {"trip": trip, "tagged": tagged or {"transactions": [], "cost": None}})


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
    preview = trip["timeline"][:_TIMELINE_PREVIEW]
    costs = await safe_get(f"/travel/trips/{trip_id}/costs")
    other_events = await safe_get(f"/travel/trips/{trip_id}/other-events", default=[])
    forecast = await safe_get(f"/travel/trips/{trip_id}/forecast")
    while_away = await safe_get(f"/travel/trips/{trip_id}/while-away")
    unlinked = await safe_get(f"/travel/trips/{trip_id}/unlinked-transactions", default=[])
    tagged = await safe_get(f"/travel/trips/{trip_id}/tagged-transactions")
    entity_costs = {
        kind: {item["id"]: item for item in (costs or {}).get(kind, [])} for kind in ("legs", "stays", "visits")
    }
    visit_days: dict[str | None, list] = {}
    for visit in trip["visits"]:
        visit_days.setdefault(visit["visit_date"], []).append(visit)
    return templates.TemplateResponse(request, "travel_trip.html", {
        "trip": trip,
        "empty_days": _empty_days(trip),
        "days": _group_by_day(preview),
        "today": local_today().isoformat(),
        "timeline_shown": len(preview),
        "timeline_total": len(trip["timeline"]),
        "visit_days": visit_days,
        "costs": costs,
        "other_events": other_events or [],
        "warning_groups": _warning_groups(trip["warnings"]),
        "preview_size": _WARNING_PREVIEW,
        "forecast": forecast,
        "while_away": while_away,
        "unlinked": unlinked or [],
        "tagged": tagged or {"transactions": [], "cost": None},
        "entity_costs": entity_costs,
        "all_visits": all_visits,
        "places": places,
        "place_kinds": _PLACE_KINDS,
        "leg_modes": _LEG_MODES,
        "zones": _ZONES,
        "default_zone": get_settings().timezone,
    })
