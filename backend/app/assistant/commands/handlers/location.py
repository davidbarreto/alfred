import logging
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, parse_bool, parse_int, parse_tags
from app.features.organizer.locations.errors import LocationConflictError, LocationValidationError
from app.features.organizer.locations.schemas import (
    LocationCreate,
    LocationFilters,
    LocationTravelTimeSet,
    LocationUpdate,
)
from app.features.organizer.locations.service import LocationService
from app.features.organizer.locations.travel_time_service import LocationTravelTimeService
from app.features.planning.schemas import parse_travel_times

logger = logging.getLogger(__name__)

_TEXT_FIELDS = ("name", "kind", "address", "maps_url", "coordinates", "opening_hours", "notes")


def _required(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} is required")
    return value


async def _fields(arguments: dict[str, Any], service: LocationService) -> dict[str, Any]:
    """Location fields present in the arguments; an empty value clears an optional field."""
    fields: dict[str, Any] = {}
    for key in _TEXT_FIELDS:
        if key in arguments:
            fields[key] = str(arguments[key] or "").strip() or None
    if "active" in arguments:
        fields["active"] = parse_bool(arguments["active"], "active")
    if "sells" in arguments:
        fields["category_ids"] = await service.category_ids_for(parse_tags(arguments["sells"]))
    return fields


async def _routes_from(arguments: dict[str, Any], travel_times: LocationTravelTimeService) -> list[tuple[int, str, int]]:
    """`--from home:metro=20,foot=35;office:car=10` as (origin_id, mode, minutes); every origin must exist already."""
    raw = str(arguments.get("travel_from") or "").strip()
    if not raw:
        return []
    try:
        entries = parse_travel_times(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"from: {exc}")
    routes = []
    for entry in entries:
        if "origin" in entry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="from: write origin:mode=minutes (the destination is this location), without '>'",
            )
        origin = await travel_times.find_location(entry["place"])
        if origin is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"from: unknown location {entry['place']!r}; add it first with location add",
            )
        routes.append((origin.id, entry["mode"], entry["minutes"]))
    return routes


async def _save_routes(location_id: int, routes: list[tuple[int, str, int]], travel_times: LocationTravelTimeService) -> None:
    for origin_id, mode, minutes in routes:
        payload = build_model(LocationTravelTimeSet, destination_id=location_id, mode=mode, minutes=minutes)
        await travel_times.set(origin_id, payload)


async def _with_travel_times(location, travel_times: LocationTravelTimeService) -> dict[str, Any]:
    result = location.model_dump(mode="json")
    result["travel_times"] = [t.model_dump(mode="json") for t in await travel_times.list_for(location.id) or []]
    return result


async def _resolve(ref: str, service: LocationService):
    location = await service.find(ref)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Location {ref!r} not found")
    return location


async def handle_location(
    command: str, arguments: dict[str, Any], service: LocationService, travel_times: LocationTravelTimeService
) -> Any:
    logger.debug("handle_location: command=%s args_keys=%s", command, list(arguments.keys()))
    try:
        return await _dispatch(command, arguments, service, travel_times)
    except LocationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except LocationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


async def _dispatch(
    command: str, arguments: dict[str, Any], service: LocationService, travel_times: LocationTravelTimeService
) -> Any:
    if command == "add":
        fields = await _fields(arguments, service)
        fields["name"] = _required(arguments, "name")
        fields = {k: v for k, v in fields.items() if v is not None}
        payload = build_model(LocationCreate, **fields)
        routes = await _routes_from(arguments, travel_times)
        location = await service.create(payload)
        await _save_routes(location.id, routes, travel_times)
        return await _with_travel_times(location, travel_times)

    if command == "list":
        include_all = parse_bool(arguments["all"], "all") if "all" in arguments else False
        category_id = None
        if str(arguments.get("sells") or "").strip():
            category_id = (await service.category_ids_for([str(arguments["sells"])]))[0]
        filters = LocationFilters(
            kind=str(arguments.get("kind") or "").strip() or None,
            active=None if include_all else True,
            category_id=category_id,
            limit=parse_int(arguments.get("limit"), "limit") or 200,
            offset=0,
        )
        return [loc.model_dump(mode="json") for loc in await service.list(filters)]

    if command == "show":
        return await _with_travel_times(await _resolve(_required(arguments, "location"), service), travel_times)

    if command == "update":
        location = await _resolve(_required(arguments, "location"), service)
        payload = build_model(LocationUpdate, **await _fields(arguments, service))
        routes = await _routes_from(arguments, travel_times)
        result = await service.update(location.id, payload)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Location {location.id} not found")
        await _save_routes(location.id, routes, travel_times)
        return await _with_travel_times(result, travel_times)

    if command == "delete":
        location = await _resolve(_required(arguments, "location"), service)
        await service.delete(location.id)
        return {"id": location.id, "name": location.name, "deleted": True}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown location command: {command}")
