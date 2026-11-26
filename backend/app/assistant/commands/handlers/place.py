"""The `place` command group: every place (everyday ones and trip ones) through one command.

What a place is goes through location's `PlaceService`, its everyday role (membership, what it sells, travel times)
through organizer, and its travel role (tags, grade, visits) through travel. This handler only composes them.
"""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, optional_int, parse_bool, parse_int, parse_tags
from app.features.location.cities.schemas import CityCreate, CityFilters
from app.features.location.cities.service import CityService
from app.features.location.errors import LocationConflictError, LocationNotFoundError, LocationValidationError
from app.features.location.places.constants import DEFAULT_KIND, HOME_KIND
from app.features.location.places.schemas import PlaceCreate, PlaceUpdate, clean_kind, parse_kind
from app.features.location.places.service import PlaceService
from app.features.organizer.everyday_places.constants import default_everyday
from app.features.organizer.everyday_places.schemas import EverydayPlaceCreate, EverydayPlaceFilters, EverydayPlaceRead
from app.features.organizer.everyday_places.service import EverydayPlaceService
from app.features.organizer.travel_times.schemas import TravelTimeSet
from app.features.organizer.travel_times.service import TravelTimeService
from app.features.planning.schemas import parse_travel_times
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.places.schemas import TravelPlaceFilters, TravelPlaceRead, TravelPlaceUpdate
from app.features.travel.places.service import TravelPlaceService
from app.features.travel.transaction_links.service import TransactionLinkService
from app.features.travel.visits.schemas import VisitCreate
from app.features.travel.visits.service import VisitService
from app.shared.utils.timezone import local_today

logger = logging.getLogger(__name__)

_TEXT_FIELDS = ("name", "kind", "address", "maps_url", "coordinates", "opening_hours", "notes")
_VIEWS = ("everyday", "visited", "planned", "all")


@dataclass(frozen=True)
class PlaceServices:
    places: PlaceService
    everyday: EverydayPlaceService
    travel_times: TravelTimeService
    travel: TravelPlaceService
    visits: VisitService
    costs: TransactionLinkService
    cities: CityService


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _text(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return None if value is None else str(value).strip() or None


def _required(arguments: dict[str, Any], key: str) -> str:
    value = _text(arguments, key)
    if not value:
        raise _bad_request(f"{key} is required")
    return value


# ---- resolving references --------------------------------------------------

async def _city_id(arguments: dict[str, Any], services: PlaceServices, create: bool) -> int | None:
    """The city `--city` names (an id or a name, narrowed by `--country`); None when no city is given.

    An unknown name is created in `--country` when `create`; a name in several countries is refused, never guessed.
    """
    ref, country = _text(arguments, "city"), _text(arguments, "country")
    if ref is None:
        if country is not None:
            raise _bad_request("country only narrows --city: give the city too")
        return None
    if ref.isdigit():
        return int(ref)
    found = await services.cities.get_cities(CityFilters(country_id=None, q=ref))
    matches = [c for c in found if c.name.lower() == ref.lower()]
    if country:
        matches = [c for c in matches if c.country.name.lower() == country.lower()]
    if len(matches) > 1:
        raise _bad_request(f"{ref} exists in several countries ({', '.join(c.country.name for c in matches)}): add --country")
    if matches:
        return matches[0].id
    if not create:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"City {ref!r} not found")
    if not country:
        raise _bad_request(f"{ref} is a new city: add --country to create it")
    return (await services.cities.create_city(build_model(CityCreate, name=ref, country=country))).id


async def _resolve(arguments: dict[str, Any], services: PlaceServices, narrow: bool = True) -> EverydayPlaceRead:
    """The place `place` names: an id, or a name (everyday places first, then the places in `--city`, by default
    the home city). Several places of that name across cities is a 409 listing them. With `narrow` off (update,
    where `--city` is the new city) the lookup ignores `--city`."""
    ref = _required(arguments, "place")
    city_id = await _city_id(arguments, services, create=False) if narrow and not ref.isdigit() else None
    if city_id is None:
        found = await services.everyday.find(ref)
    else:
        row = await services.places.find(ref, city_id)
        found = None if row is None else await services.everyday.get(row.id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Place {ref!r} not found")
    return found


async def _routes_from(arguments: dict[str, Any], services: PlaceServices) -> list[tuple[int, str, int]]:
    """`--from home:metro=20,foot=35;office:car=10` as (origin_id, mode, minutes); every origin must exist already."""
    raw = _text(arguments, "travel_from")
    if not raw:
        return []
    try:
        entries = parse_travel_times(raw)
    except ValueError as exc:
        raise _bad_request(f"from: {exc}")
    routes = []
    for entry in entries:
        if "origin" in entry:
            raise _bad_request("from: write origin:mode=minutes (the destination is this place), without '>'")
        origin = await services.travel_times.find_place(entry["place"])
        if origin is None:
            raise _bad_request(f"from: unknown place {entry['place']!r}; add it first with place add")
        routes.append((origin.id, entry["mode"], entry["minutes"]))
    return routes


async def _save_routes(place_id: int, routes: list[tuple[int, str, int]], services: PlaceServices) -> None:
    for origin_id, mode, minutes in routes:
        await services.travel_times.set(
            origin_id, build_model(TravelTimeSet, destination_id=place_id, mode=mode, minutes=minutes)
        )


# ---- reading -----------------------------------------------------------------

def _everyday_summary(place: EverydayPlaceRead) -> dict[str, Any]:
    return {
        "id": place.id, "name": place.name, "kind": place.kind, "city": place.city.name, "address": place.address,
        "everyday": place.everyday, "active": place.active, "opening_hours": place.opening_hours_text,
        "today": place.today.model_dump(mode="json") if place.today else None,
        "sells": [c.name for c in place.categories],
    }


def _travel_summary(place: TravelPlaceRead) -> dict[str, Any]:
    return {
        "id": place.id, "name": place.name, "kind": place.kind, "city": place.city.name,
        "country": place.city.country.name, "active": place.active, "grade": place.grade,
        "grade_count": place.grade_count, "tags": place.tags, "notes": place.notes, "maps_link": place.maps_link,
    }


async def _detail(place_id: int, services: PlaceServices) -> dict[str, Any]:
    """Everything about one place: what it is, its everyday role and its travel history."""
    everyday = await services.everyday.get(place_id)
    if everyday is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Place {place_id} not found")
    travel = await services.travel.get_place_detail(place_id)
    costs = await services.costs.get_place_costs(place_id)
    result = everyday.model_dump(mode="json")
    result["country"] = everyday.city.country.name
    result["sells"] = [c.name for c in everyday.categories]
    result.pop("categories", None)
    result["travel_times"] = [t.model_dump(mode="json") for t in await services.travel_times.list_for(place_id) or []]
    if travel is not None:
        result.update({
            "grade": travel.grade, "grade_count": travel.grade_count, "tags": travel.tags,
            "visits": [
                {"id": v.id, "trip_id": v.trip_id, "status": v.status, "grade": v.grade, "notes": v.notes,
                 "date": v.visit_date.isoformat() if v.visit_date else None}
                for v in travel.visits
            ],
            "stays": [
                {"id": s.id, "trip_id": s.trip_id, "grade": s.grade,
                 "check_in": s.check_in_local.isoformat(timespec="minutes"),
                 "check_out": s.check_out_local.isoformat(timespec="minutes")}
                for s in travel.stays
            ],
        })
    result["lifetime_cost"] = costs.total.model_dump(mode="json") if costs else None
    return result


async def _list(arguments: dict[str, Any], services: PlaceServices) -> dict[str, Any]:
    view = (_text(arguments, "view") or "everyday").lower()
    if view not in _VIEWS:
        raise _bad_request(f"view must be one of {', '.join(_VIEWS)}")
    include_archived = parse_bool(arguments["all"], "all") if "all" in arguments else False
    active = None if include_archived else True
    limit = optional_int(arguments, "limit", 200 if view == "everyday" else 50)
    if view == "everyday":
        travel_only = [k for k in ("city", "country", "tag", "min_grade", "ungraded") if _text(arguments, k)]
        if travel_only:
            raise _bad_request(f"{', '.join(travel_only)} filter the visited, planned or all views: add --view visited, planned or all")
        sells = _text(arguments, "sells")
        filters = EverydayPlaceFilters(
            kind=_text(arguments, "kind"), active=active,
            category_id=(await services.everyday.category_ids_for([sells]))[0] if sells else None,
            q=_text(arguments, "q"), limit=limit, offset=optional_int(arguments, "offset", 0),
        )
        places = await services.everyday.list(filters)
        return {"view": view, "count": len(places), "places": [_everyday_summary(p) for p in places]}
    if _text(arguments, "sells"):
        raise _bad_request("sells filters the everyday view")
    filters = TravelPlaceFilters(
        q=_text(arguments, "q"), kind=parse_kind(_text(arguments, "kind")), city=_text(arguments, "city"),
        country=_text(arguments, "country"), tag=parse_tags(arguments.get("tag")) or None,
        min_grade=parse_int(arguments.get("min_grade"), "min_grade"),
        ungraded=parse_bool(arguments["ungraded"], "ungraded") if _text(arguments, "ungraded") else False,
        status=view if view in ("visited", "planned") else None, active=active,
        limit=limit, offset=optional_int(arguments, "offset", 0),
    )
    places = await services.travel.get_places(filters)
    return {"view": view, "count": len(places), "places": [_travel_summary(p) for p in places]}


# ---- writing -----------------------------------------------------------------

async def _fields(arguments: dict[str, Any]) -> dict[str, Any]:
    """Base place fields present in the arguments; an empty value clears an optional field."""
    fields: dict[str, Any] = {k: _text(arguments, k) for k in _TEXT_FIELDS if k in arguments}
    if "active" in arguments:
        fields["active"] = parse_bool(arguments["active"], "active")
    return fields


def _everyday_flag(arguments: dict[str, Any]) -> bool | None:
    return parse_bool(arguments["everyday"], "everyday") if _text(arguments, "everyday") else None


def _check_everyday_only(arguments: dict[str, Any], everyday: bool) -> None:
    if not everyday and any(_text(arguments, k) for k in ("sells", "travel_from")):
        raise _bad_request("sells and from are for everyday places: add --everyday true")


async def _add(arguments: dict[str, Any], services: PlaceServices) -> dict[str, Any]:
    name = _required(arguments, "name")
    kind = clean_kind(_text(arguments, "kind") or DEFAULT_KIND)
    everyday = _everyday_flag(arguments)
    if kind == HOME_KIND and everyday is False:
        raise _bad_request("Home is always an everyday place")
    if everyday is None:
        everyday = default_everyday(kind)
    if everyday is None:
        raise _bad_request(
            f"Is {name} one of the user's everyday places (the day plan, what it sells, travel times) or a place "
            "visited once (a trip, a restaurant to grade)? Ask, then pass --everyday true or false"
        )
    _check_everyday_only(arguments, everyday)
    # Validate everything before the first write, so a typo leaves nothing half-created.
    sells = _text(arguments, "sells")
    category_ids = await services.everyday.category_ids_for(parse_tags(sells)) if sells else []
    routes = await _routes_from(arguments, services)
    tags = parse_tags(arguments.get("tags"))
    fields = {k: v for k, v in (await _fields(arguments)).items() if v is not None}
    fields.update(name=name, kind=kind)
    city_id = await _city_id(arguments, services, create=True)
    if city_id is not None:
        fields["city_id"] = city_id
    if everyday:
        place_id = (await services.everyday.create(build_model(EverydayPlaceCreate, **fields, category_ids=category_ids))).id
    else:
        place_id = (await services.places.create(build_model(PlaceCreate, **fields))).id
    if tags:
        await services.travel.update_place(place_id, TravelPlaceUpdate(tags=tags))
    await _save_routes(place_id, routes, services)
    return await _detail(place_id, services)


async def _update(arguments: dict[str, Any], services: PlaceServices) -> dict[str, Any]:
    place = await _resolve(arguments, services, narrow=False)
    fields = await _fields(arguments)
    if "city" in arguments:
        fields["city_id"] = await _city_id(arguments, services, create=True)
        if fields["city_id"] is None:
            raise _bad_request("city cannot be empty: every place has one")
    everyday = _everyday_flag(arguments)
    _check_everyday_only(arguments, place.everyday if everyday is None else everyday)
    category_ids = await services.everyday.category_ids_for(parse_tags(arguments["sells"])) if "sells" in arguments else None
    routes = await _routes_from(arguments, services)
    if everyday is True:
        await services.everyday.add(place.id)
    if fields or category_ids is not None:
        if await services.everyday.update(place.id, build_model(PlaceUpdate, **fields), category_ids) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Place {place.id} not found")
    if "tags" in arguments:
        await services.travel.update_place(place.id, TravelPlaceUpdate(tags=parse_tags(arguments.get("tags"))))
    if everyday is False:
        await services.everyday.remove(place.id)
    await _save_routes(place.id, routes, services)
    return await _detail(place.id, services)


async def _set_active(arguments: dict[str, Any], services: PlaceServices, active: bool) -> dict[str, Any]:
    place = await _resolve(arguments, services)
    await services.places.update(place.id, PlaceUpdate(active=active))
    return {"id": place.id, "name": place.name, "active": active,
            "message": f"{place.name} {'brought back' if active else 'archived'}"}


async def _grade(arguments: dict[str, Any], services: PlaceServices) -> dict[str, Any]:
    """`place grade Cafe Example 4`: a visited visit with no trip. The grade can also come as `--grade`."""
    if not _text(arguments, "grade"):
        name, _, last = _required(arguments, "place").rpartition(" ")
        if not name or not last.isdigit():
            raise _bad_request("grade is required: a whole number from 1 to 5 after the place")
        arguments = {**arguments, "place": name, "grade": last}
    place = await _resolve(arguments, services)
    day = _text(arguments, "date")
    visit = await services.visits.create_visit(build_model(
        VisitCreate, place_id=place.id, status="visited", grade=parse_int(arguments["grade"], "grade"),
        visit_date=day or local_today(), notes=_text(arguments, "notes"),
    ))
    graded = await services.travel.get_place(place.id)
    average = f"; its grade is now {graded.grade}" if graded and graded.grade is not None else ""
    return {"id": visit.id, "place_id": place.id,
            "message": f"{place.name} graded {visit.grade}/5 on {visit.visit_date}{average}"}


# ---- dispatch ------------------------------------------------------------------

async def handle_place(command: str, arguments: dict[str, Any], services: PlaceServices) -> Any:
    logger.debug("handle_place: command=%s args_keys=%s", command, list(arguments.keys()))
    try:
        return await _dispatch(command, arguments, services)
    except LocationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise _bad_request(str(exc))
    except (LocationConflictError, TravelConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or "Conflict")
    except (LocationNotFoundError, TravelNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


async def _dispatch(command: str, arguments: dict[str, Any], services: PlaceServices) -> Any:
    if command == "add":
        return await _add(arguments, services)
    if command == "list":
        return await _list(arguments, services)
    if command == "show":
        return await _detail((await _resolve(arguments, services)).id, services)
    if command == "update":
        return await _update(arguments, services)
    if command in ("archive", "unarchive"):
        return await _set_active(arguments, services, active=command == "unarchive")
    if command == "grade":
        return await _grade(arguments, services)
    if command == "delete":
        place = await _resolve(arguments, services)
        if not await services.places.delete(place.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Place {place.id} not found")
        return {"id": place.id, "name": place.name, "deleted": True}
    raise _bad_request(f"Unknown place command: {command}")
