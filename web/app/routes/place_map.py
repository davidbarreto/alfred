"""The Places map: the world page, the map data the map component fetches, and the My Maps CSV of a city or country.

The data is `GET /location/map` (location only: countries with their ISO code, cities and places with coordinates);
this module adds each pin's icon and colour group, and each city's and place's travel status from the travel lists
(`GET /travel/cities`, `GET /travel/places?status=planned`), bucketed into the map's three toggles. Registered before
the place routes, so `/places/map` is never read as a place id.
"""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.shared.forward import safe_get
from app.shared.location_kinds import MAP_GROUP_LABELS, MAP_STATUS_LABELS, location_icon, map_group
from app.shared.map_csv import map_csv_response, place_rows
from app.templates_config import templates

router = APIRouter(prefix="/places")

# UN members plus the two observer states: the "share of the world" counter's denominator.
WORLD_COUNTRIES = 195
_ALL = 500
_CSV_HEADER = ["Name", "Address", "Category", "Description"]


# Each city status (travel's `CityStatus`) and the map toggle that shows it (MAP_STATUS_LABELS). A city with no travel
# status (only links, or nothing in travel) has not been to as far as Alfred knows: it goes with the planned ones.
_CITY_BUCKETS = {"home": "visited", "lived": "visited", "visited": "visited", "planned": "planned", "passed": "passed"}


def map_data(data: dict, travel_cities: list[dict] | None = None, planned_places: list[dict] | None = None) -> dict:
    """The backend's map rows with each place's icon, colour group and status, and each city's status and born flag.

    `None` for the travel lists means travel could not be read: every pin then counts as visited, so the map still
    shows everything rather than hiding it all behind the Planned toggle.
    """
    travel = {row["id"]: row for row in travel_cities or []}
    planned = {row["id"] for row in planned_places or []}
    cities = []
    for city in data["cities"]:
        row = travel.get(city["id"])
        status = "visited" if travel_cities is None else _CITY_BUCKETS.get((row or {}).get("status"), "planned")
        if city.get("home"):
            status = "visited"
        cities.append({**city, "status": status, "born": bool(row and row.get("born"))})
    places = [
        {**p, "icon": location_icon(p["kind"]), "group": map_group(p["kind"]),
         "status": "planned" if p["id"] in planned else "visited"}
        for p in data["places"]
    ]
    return {**data, "cities": cities, "places": places}


async def _travel_statuses(data: dict, scope: dict) -> tuple[list[dict] | None, list[dict] | None]:
    """The travel city rows (status, born) and the planned places for the map's scope; None for one that failed."""
    country_id = scope.get("country_id") or (str(data["countries"][0]["id"]) if scope and data["countries"] else None)
    city_params = {"status": "all", "limit": _ALL, **({"country_id": country_id} if country_id else {})}
    place_params = {"status": "planned", "active": "true", "limit": _ALL, **scope}
    return await asyncio.gather(
        safe_get("/travel/cities", params=city_params), safe_get("/travel/places", params=place_params),
    )


def world_stats(countries: list[dict]) -> dict:
    count = len(countries)
    return {
        "countries": count,
        "cities": sum(c["city_count"] for c in countries),
        "share": round(100 * min(count, WORLD_COUNTRIES) / WORLD_COUNTRIES),
    }


def _scope(params) -> dict:
    """At most one of city_id and country_id (city wins), as the backend expects."""
    for key in ("city_id", "country_id"):
        value = params.get(key) or ""
        if value.isdigit():
            return {key: value}
    return {}


@router.get("/map", response_class=HTMLResponse)
async def map_page(request: Request):
    data = await safe_get("/location/map")
    countries = (data or {}).get("countries", [])
    return templates.TemplateResponse(request, "places_map.html", {
        "available": data is not None, "countries": countries, "stats": world_stats(countries),
        "no_code": [c for c in countries if not c["code"]], "groups": MAP_GROUP_LABELS, "statuses": MAP_STATUS_LABELS,
        "places_without_coordinates": (data or {}).get("places_without_coordinates", 0),
    })


@router.get("/map/data")
async def map_json(request: Request):
    """What `places-map.js` draws; 502 when the backend can't be reached (the map then says so)."""
    scope = _scope(request.query_params)
    data = await safe_get("/location/map", params=scope or None)
    if data is None:
        return JSONResponse({"error": "The map data could not be loaded."}, status_code=502)
    travel_cities, planned_places = await _travel_statuses(data, scope)
    return JSONResponse(map_data(data, travel_cities, planned_places), headers={"Cache-Control": "no-store"})


async def _places_csv(params: dict, filename: str):
    places = await safe_get("/location/places", params={**params, "active": "true", "limit": _ALL}, default=[])
    return map_csv_response(_CSV_HEADER, place_rows(places or []), filename)


@router.get("/cities/{city_id}/map.csv")
async def city_map_csv(city_id: int):
    city = await safe_get(f"/location/cities/{city_id}")
    if city is None:
        return RedirectResponse("/places/cities", status_code=302)
    return await _places_csv({"city_id": city_id}, f"city-{city_id}-map.csv")


@router.get("/countries/{country_id}/map.csv")
async def country_map_csv(country_id: int):
    country = await safe_get(f"/location/countries/{country_id}")
    if country is None:
        return RedirectResponse("/places/countries", status_code=302)
    return await _places_csv({"country_id": country_id}, f"country-{country_id}-map.csv")
