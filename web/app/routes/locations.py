from urllib.parse import quote_plus

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.shared.forward import forward, safe_get
from app.shared.timezone import local_today
from app.templates_config import templates

router = APIRouter(prefix="/locations")

_KINDS = ("home", "work", "school", "gym", "supermarket", "pharmacy", "bakery", "market", "other")
_DAYS = (("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"), ("thu", "Thursday"), ("fri", "Friday"),
         ("sat", "Saturday"), ("sun", "Sunday"))
_HOURS_HELP = "mon-fri 08:00-20:00; sat 09:00-13:00, 15:00-19:00; sun closed; holidays closed"
_MODES = ("foot", "metro", "bus", "train", "tram", "car", "taxi", "bike")
# Rows of a list card on the detail page; the rest are on their own page.
_CARD_LIMIT = 5


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


def maps_link(location: dict) -> str | None:
    """The saved Maps link, else a Maps search for the address (a link for the user, never an API call)."""
    if location.get("maps_url"):
        return location["maps_url"]
    if location.get("address"):
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(location['address'])}"
    return None


def group_locations(locations: list[dict]) -> list[tuple[str, list[dict]]]:
    """Home and the other anchors (selling nothing) first, then shops, then archived; empty groups dropped."""
    places = [loc for loc in locations if loc["active"] and not loc["categories"]]
    shops = [loc for loc in locations if loc["active"] and loc["categories"]]
    archived = [loc for loc in locations if not loc["active"]]
    groups = [("Places", places), ("Shops", shops), ("Archived", archived)]
    return [(title, items) for title, items in groups if items]


@router.get("", response_class=HTMLResponse)
async def locations_page(request: Request):
    locations = await safe_get("/organizer/locations")
    categories = await safe_get("/organizer/shopping-categories", default=[])
    return templates.TemplateResponse(request, "locations.html", {
        "available": locations is not None,
        "groups": group_locations(locations or []),
        "categories": categories,
        "kinds": _KINDS,
        "hours_help": _HOURS_HELP,
    })


@router.get("/{location_id}", response_class=HTMLResponse)
async def location_detail(request: Request, location_id: int):
    location = await safe_get(f"/organizer/locations/{location_id}")
    if location is None:
        return templates.TemplateResponse(
            request, "location_detail.html", {"location": None}, status_code=404,
        )
    categories = await safe_get("/organizer/shopping-categories", default=[])
    travel_times = await safe_get(f"/organizer/locations/{location_id}/travel-times", default=[])
    others = await _other_locations(location_id)
    today_key = _DAYS[local_today().weekday()][0]
    return templates.TemplateResponse(request, "location_detail.html", {
        "location": location,
        "week": week_rows(location.get("opening_hours"), today_key),
        "maps": maps_link(location),
        "categories": categories,
        "selected_ids": {c["id"] for c in location["categories"]},
        "home_moved": location["kind"] == "home" and request.query_params.get("moved") == "1",
        "travel_times": travel_times[:_CARD_LIMIT],
        "travel_times_total": len(travel_times),
        "others": others,
        "modes": _MODES,
        "kinds": _KINDS,
        "hours_help": _HOURS_HELP,
    })


@router.get("/{location_id}/travel-times", response_class=HTMLResponse)
async def location_travel_times(request: Request, location_id: int):
    location = await safe_get(f"/organizer/locations/{location_id}")
    if location is None:
        return templates.TemplateResponse(request, "location_detail.html", {"location": None}, status_code=404)
    travel_times = await safe_get(f"/organizer/locations/{location_id}/travel-times", default=[])
    return templates.TemplateResponse(request, "location_travel_times.html", {
        "location": location, "travel_times": travel_times, "others": await _other_locations(location_id), "modes": _MODES,
    })


async def _other_locations(location_id: int) -> list[dict]:
    """Active locations a travel time from this one can go to."""
    locations = await safe_get("/organizer/locations", params={"active": "true"}, default=[])
    return [loc for loc in locations or [] if loc["id"] != location_id]


@router.post("")
async def create_location(request: Request):
    return await forward(api.post("/organizer/locations", json=await request.json()), "Could not add the location.")


@router.patch("/{location_id}")
async def update_location(location_id: int, request: Request):
    return await forward(
        api.patch(f"/organizer/locations/{location_id}", json=await request.json()), "Could not save the location."
    )


@router.delete("/{location_id}")
async def delete_location(location_id: int):
    return await forward(api.delete(f"/organizer/locations/{location_id}"), "Could not delete the location.")


@router.put("/{location_id}/travel-times")
async def set_travel_time(location_id: int, request: Request):
    return await forward(
        api.put(f"/organizer/locations/{location_id}/travel-times", json=await request.json()),
        "Could not save the travel time.",
    )


@router.delete("/travel-times/{travel_time_id}")
async def delete_travel_time(travel_time_id: int):
    return await forward(
        api.delete(f"/organizer/locations/travel-times/{travel_time_id}"), "Could not delete the travel time."
    )
