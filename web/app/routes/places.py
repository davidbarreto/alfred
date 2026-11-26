"""The Places section: every place, everyday and visited, on one list and one page per place.

A place page composes three views of the same id (`docs/modules/places.md`): the place itself and its everyday role
from `/organizer/places/{id}`, and its travel history from `/travel/places/{id}`.
"""
import asyncio
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.client as api
from app.shared.forward import forward, safe_get
from app.shared.link_groups import LINK_KINDS, LINKS_PREVIEW, link_groups
from app.shared.location_kinds import EVERYDAY_KINDS, KINDS
from app.shared.timezone import local_today
from app.templates_config import templates

router = APIRouter(prefix="/places")
# The pre-Places URLs, kept as permanent redirects (place ids did not change when locations became places).
legacy_router = APIRouter(prefix="/locations")

VIEWS = ("everyday", "visited", "planned", "all")
_PAGE_SIZE = 24
_DAYS = (("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"), ("thu", "Thursday"), ("fri", "Friday"),
         ("sat", "Saturday"), ("sun", "Sunday"))
_HOURS_HELP = "mon-fri 08:00-20:00; sat 09:00-13:00, 15:00-19:00; sun closed; holidays closed"
_MODES = ("foot", "metro", "bus", "train", "tram", "car", "taxi", "bike")
# Rows of a list card on the detail page; the rest are on their own page.
_CARD_LIMIT = 5
# How far ahead a place lists its events (recurring ones are expanded into occurrences).
_EVENTS_AHEAD_DAYS = 60


def _ranges_text(ranges: list | None) -> str:
    if ranges is None:
        return "unknown"
    if not ranges:
        return "closed"
    return ", ".join(f"{start}-{end}" for start, end in ranges)


def week_rows(opening_hours: dict | None, today_key: str) -> list[dict]:
    """One row per weekday plus holidays: label, hours text, and whether it is today."""
    hours = opening_hours or {}
    rows = [
        {"label": label, "hours": _ranges_text(hours.get(key)), "today": key == today_key}
        for key, label in _DAYS
    ]
    rows.append({"label": "Public holidays", "hours": _ranges_text(hours.get("hol")), "today": False})
    return rows


def _digits(value: str | None) -> str:
    return value if (value or "").isdigit() else ""


def list_filters(params) -> dict:
    """The list's view and filters from the query string; unknown values fall back to the defaults."""
    view = params.get("view")
    return {
        "view": view if view in VIEWS else "everyday",
        "q": (params.get("q") or "").strip(),
        "kind": params.get("kind") if params.get("kind") in KINDS else "",
        "city_id": _digits(params.get("city_id")),
        "country_id": _digits(params.get("country_id")),
        "archived": params.get("archived") in ("1", "true", "on"),
        # Travel filters: the visited, planned and all views only.
        "tags": [t for t in params.getlist("tag") if t],
        "min_grade": params.get("min_grade") if params.get("min_grade") in ("1", "2", "3", "4", "5") else "",
        "ungraded": params.get("ungraded") in ("1", "true", "on"),
    }


def list_query(filters: dict) -> str:
    """The filters as a query string, for the pagination buttons and the view chips."""
    pairs = [(k, filters[k]) for k in ("view", "q", "kind", "city_id", "country_id", "min_grade")]
    pairs += [("tag", t) for t in filters["tags"]]
    pairs += [(k, "1") for k in ("archived", "ungraded") if filters[k]]
    return urlencode([(k, v) for k, v in pairs if v])


def list_request(filters: dict, offset: int) -> tuple[str, list[tuple[str, object]]]:
    """The backend path and params for one page (one row more than shown, to know there is a next page)."""
    params: list[tuple[str, object]] = [("limit", _PAGE_SIZE + 1), ("offset", offset)]
    if not filters["archived"]:
        params.append(("active", "true"))
    for key in ("q", "kind", "city_id"):
        if filters[key]:
            params.append((key, filters[key]))
    if filters["view"] == "everyday":
        return "/organizer/places", params
    if filters["country_id"]:
        params.append(("country_id", filters["country_id"]))
    if filters["min_grade"]:
        params.append(("min_grade", filters["min_grade"]))
    params += [("tag", t) for t in filters["tags"]]
    if filters["ungraded"]:
        params.append(("ungraded", "true"))
    if filters["view"] in ("visited", "planned"):
        params.append(("status", filters["view"]))
    return "/travel/places", params


async def _list_context(filters: dict, offset: int) -> dict:
    path, params = list_request(filters, offset)
    places = await safe_get(path, params=params)
    rows = places or []
    return {
        "places": rows[:_PAGE_SIZE], "available": places is not None, "filters": filters, "offset": offset,
        "has_next": len(rows) > _PAGE_SIZE, "has_prev": offset > 0, "page_size": _PAGE_SIZE,
        "query": list_query(filters),
    }


def _offset(raw: str | None) -> int:
    return int(raw) if (raw or "").isdigit() else 0


@router.get("", response_class=HTMLResponse)
async def places_page(request: Request):
    filters = list_filters(request.query_params)
    context, cities, categories, tags, homes = await asyncio.gather(
        _list_context(filters, 0),
        safe_get("/location/cities", params={"limit": 500}, default=[]),
        safe_get("/organizer/shopping-categories", default=[]),
        safe_get("/travel/tags", default=[]),
        safe_get("/location/places", params={"kind": "home"}, default=[]),
    )
    return templates.TemplateResponse(request, "places.html", {
        **context, "cities": cities or [], "categories": categories or [], "all_tags": [t["name"] for t in tags or []],
        "home_city": homes[0]["city"] if homes else None,
        "kinds": KINDS, "everyday_kinds": sorted(EVERYDAY_KINDS), "hours_help": _HOURS_HELP,
        "views": [(v, list_query({**filters, "view": v})) for v in VIEWS],
    })


@router.get("/list", response_class=HTMLResponse)
async def places_list(request: Request):
    filters = list_filters(request.query_params)
    context = await _list_context(filters, _offset(request.query_params.get("offset")))
    return templates.TemplateResponse(request, "_places_list.html", context)


async def _place(place_id: int) -> dict | None:
    """The place with its everyday role (any place: `everyday` says whether it is one)."""
    return await safe_get(f"/organizer/places/{place_id}")


def _not_found(request: Request):
    return templates.TemplateResponse(request, "place_detail.html", {"place": None}, status_code=404)


@router.get("/{place_id}", response_class=HTMLResponse)
async def place_detail(request: Request, place_id: int):
    place, travel, categories, costs, links = await asyncio.gather(
        _place(place_id),
        safe_get(f"/travel/places/{place_id}"),
        safe_get("/organizer/shopping-categories", default=[]),
        safe_get(f"/travel/places/{place_id}/costs"),
        safe_get(f"/travel/places/{place_id}/links", default=[]),
    )
    if place is None:
        return _not_found(request)
    travel = travel or {"tags": [], "grade": None, "grade_count": 0, "visits": [], "stays": []}
    travel_times, others, events = [], [], []
    if place["everyday"]:
        travel_times, others, events = await asyncio.gather(
            safe_get(f"/organizer/places/{place_id}/travel-times", default=[]),
            _other_places(place_id),
            upcoming_events(place_id),
        )
    links = links or []
    visits, stays = travel["visits"], travel["stays"]
    today_key = _DAYS[local_today().weekday()][0]
    return templates.TemplateResponse(request, "place_detail.html", {
        "place": place, "travel": travel,
        "week": week_rows(place.get("opening_hours"), today_key),
        "categories": categories or [],
        "selected_ids": {c["id"] for c in place["categories"]},
        "home_moved": place["kind"] == "home" and request.query_params.get("moved") == "1",
        "editing": request.query_params.get("edit") == "1",
        "travel_times": (travel_times or [])[:_CARD_LIMIT], "travel_times_total": len(travel_times or []),
        "others": others,
        "events": events[:_CARD_LIMIT], "events_total": len(events),
        "visits": visits[:_CARD_LIMIT], "stays": stays[:_CARD_LIMIT], "history_total": len(visits) + len(stays),
        "wishlisted": any(v["status"] == "planned" and not v["visit_date"] for v in visits),
        "today": local_today().isoformat(),
        "place_cost": costs["total"] if costs else None,
        "entity_costs": {"visits": {c["id"]: c for c in (costs or {}).get("visits", [])}},
        "web_links": links, "link_kinds": LINK_KINDS, "links_preview": LINKS_PREVIEW,
        "link_groups": await link_groups([place["city"]], {link["url"] for link in links}, with_countries=False),
        "modes": _MODES, "kinds": KINDS, "everyday_kinds": sorted(EVERYDAY_KINDS), "hours_help": _HOURS_HELP,
    })


@router.get("/{place_id}/travel-times", response_class=HTMLResponse)
async def place_travel_times(request: Request, place_id: int):
    place = await _place(place_id)
    if place is None:
        return _not_found(request)
    travel_times = await safe_get(f"/organizer/places/{place_id}/travel-times", default=[])
    return templates.TemplateResponse(request, "place_travel_times.html", {
        "place": place, "travel_times": travel_times, "others": await _other_places(place_id), "modes": _MODES,
    })


@router.get("/{place_id}/events", response_class=HTMLResponse)
async def place_events(request: Request, place_id: int):
    place = await _place(place_id)
    if place is None:
        return _not_found(request)
    return templates.TemplateResponse(request, "place_events.html", {
        "place": place, "events": await upcoming_events(place_id), "days": _EVENTS_AHEAD_DAYS,
    })


@router.get("/{place_id}/visits", response_class=HTMLResponse)
async def place_visits(request: Request, place_id: int):
    """Every visit and stay of a place (the place page shows the first 5 of each)."""
    travel = await safe_get(f"/travel/places/{place_id}")
    if travel is None:
        return _not_found(request)
    costs = await safe_get(f"/travel/places/{place_id}/costs")
    return templates.TemplateResponse(request, "place_visits.html", {
        "place": travel, "visits": travel["visits"], "stays": travel["stays"],
        "entity_costs": {"visits": {c["id"]: c for c in (costs or {}).get("visits", [])}},
    })


@router.get("/{place_id}/links", response_class=HTMLResponse)
async def place_links(request: Request, place_id: int):
    place = await _place(place_id)
    if place is None:
        return _not_found(request)
    links = await safe_get(f"/travel/places/{place_id}/links", default=[])
    return templates.TemplateResponse(request, "travel_links.html", {
        "owner_kind": "place", "owner_id": place_id, "owner_name": place["name"], "back_url": f"/places/{place_id}",
        "web_links": links, "link_kinds": LINK_KINDS,
    })


async def upcoming_events(place_id: int) -> list[dict]:
    """Timed and all-day events at this place from today through the next 60 days, each occurrence listed."""
    today = local_today()
    params = {
        "place_id": place_id,
        "start_from": datetime.combine(today, time.min).isoformat(),
        "start_to": datetime.combine(today + timedelta(days=_EVENTS_AHEAD_DAYS), time.max).isoformat(timespec="seconds"),
        "limit": 500,
    }
    events = await safe_get("/organizer/calendar-events", params=params, default=[])
    return sorted(events or [], key=lambda e: e["start_datetime"])


async def _other_places(place_id: int) -> list[dict]:
    """Active everyday places a travel time from this one can go to."""
    places = await safe_get("/organizer/places", params={"active": "true"}, default=[])
    return [p for p in places or [] if p["id"] != place_id]


async def _create(body: dict) -> dict:
    """An everyday place goes through the everyday API (with what it sells), any other through the base one;
    travel tags are added after."""
    everyday = bool(body.pop("everyday", False))
    tags = body.pop("tags", None) or []
    category_ids = body.pop("category_ids", None) or []
    if everyday:
        created = await api.post("/organizer/places", json={**body, "category_ids": category_ids})
    else:
        created = await api.post("/location/places", json=body)
    if tags:
        await api.patch(f"/travel/places/{created['id']}", json={"tags": tags})
    return {"id": created["id"]}


async def _save(place_id: int, body: dict) -> dict:
    """The place's own fields to the location API, the everyday role and what it sells to organizer, the tags to
    travel; returns the place as the everyday view sees it."""
    everyday = body.pop("everyday", None)
    category_ids = body.pop("category_ids", None)
    tags = body.pop("tags", None)
    if body:
        await api.patch(f"/location/places/{place_id}", json=body)
    if everyday is True:
        await api.put(f"/organizer/places/{place_id}")
    elif everyday is False:
        await api.delete(f"/organizer/places/{place_id}")
    if category_ids is not None and everyday is not False:
        await api.put(f"/organizer/places/{place_id}/categories", json={"category_ids": category_ids})
    if tags is not None:
        await api.patch(f"/travel/places/{place_id}", json={"tags": tags})
    return await api.get(f"/organizer/places/{place_id}")


@router.post("")
async def create_place(request: Request):
    """A new place; its city defaults to the Home place's."""
    return await forward(_create(await request.json()), "Could not add the place.")


@router.patch("/{place_id}")
async def update_place(place_id: int, request: Request):
    return await forward(_save(place_id, await request.json()), "Could not save the place.")


@router.delete("/{place_id}")
async def delete_place(place_id: int):
    return await forward(api.delete(f"/location/places/{place_id}"), "Could not delete the place.")


@router.put("/{place_id}/travel-times")
async def set_travel_time(place_id: int, request: Request):
    return await forward(
        api.put(f"/organizer/places/{place_id}/travel-times", json=await request.json()),
        "Could not save the travel time.",
    )


@router.delete("/travel-times/{travel_time_id}")
async def delete_travel_time(travel_time_id: int):
    return await forward(
        api.delete(f"/organizer/travel-times/{travel_time_id}"), "Could not delete the travel time."
    )


@legacy_router.get("")
async def legacy_list():
    return RedirectResponse("/places", status_code=301)


@legacy_router.get("/{rest:path}")
async def legacy_page(rest: str):
    return RedirectResponse(f"/places/{rest}", status_code=301)
