"""Cities and countries in the Places section: cover cards, one page per city and per country.

`location` owns them (name, country, ISO code, coordinates, cover); travel adds what was done there (trips, days,
spend), from `/travel/cities` and `/travel/countries`. The pages compose both (`docs/modules/places.md`).
Registered before the place routes, so `/places/cities` is never read as a place id.
"""
import asyncio
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import app.client as api
from app.shared.forward import forward, safe_get
from app.shared.link_groups import LINK_KINDS, LINKS_PREVIEW
from app.shared.location_kinds import MAP_GROUP_LABELS
from app.shared.timezone import local_today
from app.templates_config import templates

router = APIRouter(prefix="/places")

_PAGE_SIZE = 24
# Rows of a list card on a detail page; the rest are on their own page.
_CARD_LIMIT = 5
CITY_SORTS = {"name": "Name", "last_visit": "Last visit", "trips": "Trips", "nights": "Nights", "spend": "Spend"}
# Rows per page of a city's or country's stays or legs.
_ROWS_PAGE = 20
# Enough for every city or travel row in one call: the lists are sorted by travel figures, so they page here.
_ALL = 500
_COVER_CACHE = "private, max-age=86400"


def _digits(value: str | None) -> str:
    return value if (value or "").isdigit() else ""


def _offset(raw: str | None) -> int:
    return int(raw) if (raw or "").isdigit() else 0


def by_id(rows: list[dict] | None) -> dict[int, dict]:
    return {row["id"]: row for row in rows or []}


def sort_cards(cards: list[dict], sort: str) -> list[dict]:
    """By name; by last visit (latest first, never visited last); or by trips, nights or spend (most first), then by name."""
    cards = sorted(cards, key=lambda c: c["item"]["name"].lower())
    if sort == "last_visit":
        dated = sorted((c for c in cards if c["travel"] and c["travel"]["last_visit"]),
                       key=lambda c: c["travel"]["last_visit"], reverse=True)
        return dated + [c for c in cards if c not in dated]
    if sort in ("trips", "nights", "spend"):
        field = "spend_eur" if sort == "spend" else sort
        return sorted(cards, key=lambda c: float((c["travel"] or {}).get(field) or 0), reverse=True)
    return cards


def cities_filters(params) -> dict:
    return {
        "q": (params.get("q") or "").strip(),
        "country_id": _digits(params.get("country_id")),
        "sort": params.get("sort") if params.get("sort") in CITY_SORTS else "name",
    }


def _query(filters: dict) -> str:
    return urlencode([(k, v) for k, v in filters.items() if v and not (k == "sort" and v == "name")])


async def _home_city_id() -> int | None:
    homes = await safe_get("/location/places", params={"kind": "home"}, default=[])
    return homes[0]["city"]["id"] if homes else None


def _page(cards: list[dict], offset: int) -> dict:
    return {
        "cards": cards[offset:offset + _PAGE_SIZE], "total": len(cards), "offset": offset,
        "has_prev": offset > 0, "has_next": offset + _PAGE_SIZE < len(cards), "page_size": _PAGE_SIZE,
    }


async def _city_cards_context(filters: dict, offset: int) -> dict:
    params = {k: filters[k] for k in ("q", "country_id") if filters[k]}
    cities, travel, home_city_id = await asyncio.gather(
        safe_get("/location/cities", params=params or None),
        safe_get("/travel/cities", params={"limit": _ALL}, default=[]),
        _home_city_id(),
    )
    rows = by_id(travel)
    cards = [{"item": c, "travel": rows.get(c["id"]), "home": c["id"] == home_city_id} for c in cities or []]
    home_places = None
    if any(card["home"] for card in cards):
        found = await safe_get("/location/places", params={"city_id": home_city_id, "active": "true", "limit": _ALL}, default=[])
        home_places = len(found or [])
    return {
        **_page(sort_cards(cards, filters["sort"]), offset), "available": cities is not None, "filters": filters,
        "query": _query(filters), "home_places": home_places,
    }


# ---- cities -------------------------------------------------------------------

@router.get("/cities", response_class=HTMLResponse)
async def cities_page(request: Request):
    filters = cities_filters(request.query_params)
    context, countries = await asyncio.gather(
        _city_cards_context(filters, 0), safe_get("/location/countries", default=[]),
    )
    return templates.TemplateResponse(request, "places_cities.html", {
        **context, "countries": countries or [], "sorts": CITY_SORTS,
    })


@router.get("/cities/list", response_class=HTMLResponse)
async def cities_list(request: Request):
    filters = cities_filters(request.query_params)
    context = await _city_cards_context(filters, _offset(request.query_params.get("offset")))
    return templates.TemplateResponse(request, "_places_city_cards.html", context)


async def _city(city_id: int) -> tuple[dict | None, dict | None]:
    """The city as location has it, and travel's view of it (None when travel can't be reached)."""
    return await asyncio.gather(safe_get(f"/location/cities/{city_id}"), safe_get(f"/travel/cities/{city_id}"))


def _not_found(request: Request, what: str):
    return templates.TemplateResponse(request, "place_geo_missing.html", {"what": what}, status_code=404)


def _albums(trips: list[dict]) -> list[dict]:
    return [t for t in trips if t.get("photo_album_url")]


@router.get("/cities/{city_id}", response_class=HTMLResponse)
async def city_page(request: Request, city_id: int):
    (city, travel), places, links, countries, home_city_id, legs = await asyncio.gather(
        _city(city_id),
        safe_get("/location/places", params={"city_id": city_id, "active": "true", "limit": _ALL}, default=[]),
        safe_get(f"/travel/cities/{city_id}/links", default=[]),
        safe_get("/location/countries", default=[]),
        _home_city_id(),
        safe_get(f"/travel/cities/{city_id}/legs", params={"limit": _CARD_LIMIT}, default=[]),
    )
    if city is None:
        return _not_found(request, "city")
    travel = travel or {"trips": [], "nights": 0, "stay_count": 0, "leg_count": 0, "grade": None, "grade_count": 0,
                        "place_count": 0, "costs": None}
    trips = travel["trips"]
    places = places or []
    return templates.TemplateResponse(request, "places_city.html", {
        "city": city, "travel": travel, "home": city_id == home_city_id,
        "places": places[:_CARD_LIMIT], "places_total": len(places),
        "trips": trips[:_CARD_LIMIT], "trips_total": len(trips),
        "legs": (legs or [])[:_CARD_LIMIT], "legs_total": travel.get("leg_count", 0),
        "albums": _albums(trips)[:_CARD_LIMIT], "albums_total": len(_albums(trips)),
        "web_links": links or [], "link_kinds": LINK_KINDS, "links_preview": LINKS_PREVIEW,
        "countries": countries or [], "today": local_today().isoformat(), "groups": MAP_GROUP_LABELS,
    })


# ---- stays and legs pages (the rows behind the nights and the legs card) ------------

async def _rows_context(owner: str, owner_id: int, kind: str, offset: int) -> dict:
    rows = await safe_get(f"/travel/{owner}/{owner_id}/{kind}", params={"limit": _ROWS_PAGE + 1, "offset": offset})
    items = rows or []
    return {
        "kind": kind, "rows": items[:_ROWS_PAGE], "available": rows is not None, "offset": offset,
        "has_prev": offset > 0, "has_next": len(items) > _ROWS_PAGE, "page_size": _ROWS_PAGE,
        "list_url": f"/places/{owner}/{owner_id}/{kind}/list", "show_city": owner == "countries",
    }


async def _rows_page(request: Request, owner: str, owner_id: int, kind: str):
    what = "city" if owner == "cities" else "country"
    base, travel, context = await asyncio.gather(
        safe_get(f"/location/{owner}/{owner_id}"), safe_get(f"/travel/{owner}/{owner_id}"),
        _rows_context(owner, owner_id, kind, 0),
    )
    if base is None:
        return _not_found(request, what)
    total = (travel or {}).get("stay_count" if kind == "stays" else "leg_count", 0)
    return templates.TemplateResponse(request, "places_geo_rows.html", {
        **context, "name": base["name"], "back_url": f"/places/{owner}/{owner_id}", "total": total,
    })


async def _rows_list(request: Request, owner: str, owner_id: int, kind: str):
    context = await _rows_context(owner, owner_id, kind, _offset(request.query_params.get("offset")))
    return templates.TemplateResponse(request, "_place_geo_rows.html", context)


@router.get("/cities/{city_id}/stays", response_class=HTMLResponse)
async def city_stays(request: Request, city_id: int):
    return await _rows_page(request, "cities", city_id, "stays")


@router.get("/cities/{city_id}/stays/list", response_class=HTMLResponse)
async def city_stays_list(request: Request, city_id: int):
    return await _rows_list(request, "cities", city_id, "stays")


@router.get("/cities/{city_id}/legs", response_class=HTMLResponse)
async def city_legs(request: Request, city_id: int):
    return await _rows_page(request, "cities", city_id, "legs")


@router.get("/cities/{city_id}/legs/list", response_class=HTMLResponse)
async def city_legs_list(request: Request, city_id: int):
    return await _rows_list(request, "cities", city_id, "legs")


@router.get("/countries/{country_id}/stays", response_class=HTMLResponse)
async def country_stays(request: Request, country_id: int):
    return await _rows_page(request, "countries", country_id, "stays")


@router.get("/countries/{country_id}/stays/list", response_class=HTMLResponse)
async def country_stays_list(request: Request, country_id: int):
    return await _rows_list(request, "countries", country_id, "stays")


@router.get("/cities/{city_id}/links", response_class=HTMLResponse)
async def city_links(request: Request, city_id: int):
    city = await safe_get(f"/location/cities/{city_id}")
    if city is None:
        return _not_found(request, "city")
    links = await safe_get(f"/travel/cities/{city_id}/links", default=[])
    return templates.TemplateResponse(request, "travel_links.html", {
        "owner_kind": "city", "owner_id": city_id, "owner_name": city["name"], "back_url": f"/places/cities/{city_id}",
        "web_links": links or [], "link_kinds": LINK_KINDS,
    })


@router.get("/cities/{city_id}/albums", response_class=HTMLResponse)
async def city_albums(request: Request, city_id: int):
    city, travel = await _city(city_id)
    if city is None:
        return _not_found(request, "city")
    return templates.TemplateResponse(request, "places_albums.html", {
        "name": city["name"], "back_url": f"/places/cities/{city_id}", "albums": _albums((travel or {}).get("trips", [])),
    })


@router.patch("/cities/{city_id}")
async def update_city(city_id: int, request: Request):
    return await forward(api.patch(f"/location/cities/{city_id}", json=await request.json()), "Could not save the city.")


@router.delete("/cities/{city_id}")
async def delete_city(city_id: int):
    return await forward(api.delete(f"/location/cities/{city_id}"), "Could not delete the city.")


# ---- countries ----------------------------------------------------------------

def mosaic(cities: list[dict], limit: int = 4) -> list[int]:
    """Ids of up to four of the country's cities that have a cover, by name: the country card's 2x2 mosaic."""
    return [c["id"] for c in sorted(cities, key=lambda c: c["name"].lower()) if c.get("has_cover")][:limit]


@router.get("/countries", response_class=HTMLResponse)
async def countries_page(request: Request):
    q = (request.query_params.get("q") or "").strip()
    sort = request.query_params.get("sort") if request.query_params.get("sort") in CITY_SORTS else "name"
    countries, cities, travel = await asyncio.gather(
        safe_get("/location/countries"),
        safe_get("/location/cities", default=[]),
        safe_get("/travel/countries", params={"limit": _ALL}, default=[]),
    )
    rows = by_id(travel)
    cards = []
    for country in countries or []:
        if q and q.lower() not in country["name"].lower():
            continue
        own = [c for c in cities or [] if c["country"]["id"] == country["id"]]
        cards.append({"item": country, "travel": rows.get(country["id"]), "city_count": len(own), "mosaic": mosaic(own)})
    offset = _offset(request.query_params.get("offset"))
    return templates.TemplateResponse(request, "places_countries.html", {
        **_page(sort_cards(cards, sort), offset), "available": countries is not None, "q": q, "sort": sort,
        "sorts": CITY_SORTS, "query": urlencode([(k, v) for k, v in (("q", q), ("sort", sort)) if v and v != "name"]),
    })


@router.get("/countries/{country_id}", response_class=HTMLResponse)
async def country_page(request: Request, country_id: int):
    country, travel, cities, links = await asyncio.gather(
        safe_get(f"/location/countries/{country_id}"),
        safe_get(f"/travel/countries/{country_id}"),
        safe_get("/location/cities", params={"country_id": country_id}, default=[]),
        safe_get(f"/travel/countries/{country_id}/links", default=[]),
    )
    if country is None:
        return _not_found(request, "country")
    travel = travel or {"trips": [], "nights": 0, "stay_count": 0, "cities": [], "grade": None, "grade_count": 0, "costs": None}
    trips, cities = travel["trips"], cities or []
    travel_cities = by_id(travel["cities"])
    return templates.TemplateResponse(request, "places_country.html", {
        "country": country, "travel": travel, "mosaic": mosaic(cities),
        "cities": [{**c, "travel": travel_cities.get(c["id"])} for c in cities[:_CARD_LIMIT]], "cities_total": len(cities),
        "trips": trips[:_CARD_LIMIT], "trips_total": len(trips),
        "albums": _albums(trips)[:_CARD_LIMIT], "albums_total": len(_albums(trips)),
        "web_links": links or [], "link_kinds": LINK_KINDS, "links_preview": LINKS_PREVIEW,
        "today": local_today().isoformat(), "groups": MAP_GROUP_LABELS,
    })


@router.get("/countries/{country_id}/links", response_class=HTMLResponse)
async def country_links(request: Request, country_id: int):
    country = await safe_get(f"/location/countries/{country_id}")
    if country is None:
        return _not_found(request, "country")
    links = await safe_get(f"/travel/countries/{country_id}/links", default=[])
    return templates.TemplateResponse(request, "travel_links.html", {
        "owner_kind": "country", "owner_id": country_id, "owner_name": country["name"],
        "back_url": f"/places/countries/{country_id}", "web_links": links or [], "link_kinds": LINK_KINDS,
    })


@router.get("/countries/{country_id}/albums", response_class=HTMLResponse)
async def country_albums(request: Request, country_id: int):
    country, travel = await asyncio.gather(
        safe_get(f"/location/countries/{country_id}"), safe_get(f"/travel/countries/{country_id}"),
    )
    if country is None:
        return _not_found(request, "country")
    return templates.TemplateResponse(request, "places_albums.html", {
        "name": country["name"], "back_url": f"/places/countries/{country_id}",
        "albums": _albums((travel or {}).get("trips", [])),
    })


@router.patch("/countries/{country_id}")
async def update_country(country_id: int, request: Request):
    return await forward(api.patch(f"/location/countries/{country_id}", json=await request.json()), "Could not save the country.")


@router.delete("/countries/{country_id}")
async def delete_country(country_id: int):
    return await forward(api.delete(f"/location/countries/{country_id}"), "Could not delete the country.")


# ---- covers (both kinds) --------------------------------------------------------

def _owner_path(kind: str, owner_id: int) -> str:
    return f"/location/{'cities' if kind == 'cities' else 'countries'}/{owner_id}/cover"


async def _cover_image(kind: str, owner_id: int) -> Response:
    try:
        content, content_type = await api.get_bytes(_owner_path(kind, owner_id))
    except httpx.HTTPError:
        return Response(status_code=404)
    return Response(content=content, media_type=content_type, headers={"Cache-Control": _COVER_CACHE})


async def _set_cover(kind: str, owner_id: int, request: Request) -> JSONResponse:
    """A file from the page's upload input, or an image URL typed into it, sent on as multipart."""
    form = await request.form()
    upload, url = form.get("file"), (form.get("url") or "").strip()
    if upload is not None and hasattr(upload, "read"):
        files = {"file": (upload.filename or "cover", await upload.read(), upload.content_type or "application/octet-stream")}
        call = api.put_multipart(_owner_path(kind, owner_id), files=files)
    elif url:
        call = api.put_multipart(_owner_path(kind, owner_id), data={"url": url})
    else:
        return JSONResponse({"error": "Choose an image or paste an image address."}, status_code=422)
    return await forward(call, "Could not save the cover.")


@router.get("/cities/{city_id}/cover")
async def city_cover(city_id: int):
    return await _cover_image("cities", city_id)


@router.put("/cities/{city_id}/cover")
async def set_city_cover(city_id: int, request: Request):
    return await _set_cover("cities", city_id, request)


@router.post("/cities/{city_id}/cover/find")
async def find_city_cover(city_id: int):
    return await forward(api.post(f"/location/cities/{city_id}/cover/find", timeout=30.0), "Could not find a photo.")


@router.delete("/cities/{city_id}/cover")
async def remove_city_cover(city_id: int):
    return await forward(api.delete(_owner_path("cities", city_id)), "Could not remove the cover.")


@router.get("/countries/{country_id}/cover")
async def country_cover(country_id: int):
    return await _cover_image("countries", country_id)


@router.put("/countries/{country_id}/cover")
async def set_country_cover(country_id: int, request: Request):
    return await _set_cover("countries", country_id, request)


@router.delete("/countries/{country_id}/cover")
async def remove_country_cover(country_id: int):
    return await forward(api.delete(_owner_path("countries", country_id)), "Could not remove the cover.")


@router.get("/cities/{city_id}/trips")
async def city_trips(city_id: int):
    """The city's trips are the travel list filtered by its name."""
    city = await safe_get(f"/location/cities/{city_id}")
    if city is None:
        return RedirectResponse("/places/cities", status_code=302)
    return RedirectResponse(f"/travel?{urlencode({'status': 'all', 'city': city['name']})}", status_code=302)


@router.get("/countries/{country_id}/trips")
async def country_trips(country_id: int):
    country = await safe_get(f"/location/countries/{country_id}")
    if country is None:
        return RedirectResponse("/places/countries", status_code=302)
    return RedirectResponse(f"/travel?{urlencode({'status': 'all', 'country': country['name']})}", status_code=302)
