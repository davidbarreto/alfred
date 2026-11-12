import logging
from dataclasses import dataclass
from datetime import date, time
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, optional_int, parse_int, parse_tags, require_int
from app.features.travel.constants import TRIP_STATUS_FILTERS
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.default_tags import TripDefaultTagService
from app.features.travel.legs.schemas import LegCreate, LegRead, LegUpdate
from app.features.travel.legs.service import LegService
from app.features.travel.recap.service import TripRecapService
from app.features.travel.places.schemas import PlaceCreate, PlaceFilters, PlaceRead, PlaceUpdate
from app.features.travel.places.service import PlaceInUseError, PlaceService
from app.features.travel.stays.schemas import StayCreate, StayRead, StayUpdate
from app.features.travel.stays.service import StayService
from app.features.travel.transaction_links.service import TransactionLinkService, TransferNotLinkableError
from app.features.travel.trips.schemas import TripCreate, TripFilters, TripRead, TripUpdate
from app.features.travel.trips.service import TripService
from app.features.travel.visits.schemas import VisitCreate, VisitFilters, VisitRead, VisitUpdate
from app.features.travel.visits.service import VisitService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TravelServices:
    trips: TripService
    legs: LegService
    stays: StayService
    places: PlaceService
    visits: VisitService
    links: TransactionLinkService
    default_tags: TripDefaultTagService
    recap: TripRecapService


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found(what: str, ref: Any) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} {ref} not found")


def _text(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return None if value is None else str(value).strip() or None


def _present(arguments: dict[str, Any], keys: tuple[str, ...]) -> dict[str, str | None]:
    """The given keys that were passed; an empty value is kept as None, which clears the field on update."""
    return {k: _text(arguments, k) for k in keys if k in arguments}


def _flag(arguments: dict[str, Any], key: str) -> bool:
    return str(arguments.get(key, "")).strip().lower() in ("1", "true", "yes", "on")


def _date(value: str | None, name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _bad_request(f"{name} must be a date as YYYY-MM-DD, got {value!r}")


def _time(value: str | None, name: str) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise _bad_request(f"{name} must be a time as HH:MM, got {value!r}")


def _float(value: str | None, name: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        raise _bad_request(f"{name} must be a number, got {value!r}")


# "my next trip" has no name to search for: it means the soonest upcoming or ongoing trip.
_NEXT_WORDS = ("next", "upcoming", "current")


def _is_id(ref: str) -> bool:
    return ref.isdigit()


# ---- resolving references --------------------------------------------------

async def _find_trip(services: TravelServices, ref: str) -> TripRead:
    """A trip by id, or by name: the soonest current trip whose name contains the text, else the latest past one."""
    if _is_id(ref):
        trip = await services.trips.get_trip(int(ref))
        if trip is None:
            raise _not_found("Trip", ref)
        return trip
    if ref.lower() in _NEXT_WORDS:
        found = await services.trips.get_trips(TripFilters(status="current", tag=None, q=None, date_from=None, date_to=None, limit=1, offset=0))
        if found:
            return found[0]
        raise _not_found("Trip", "(no upcoming trip)")
    for scope in ("current", "past"):
        found = await services.trips.get_trips(TripFilters(status=scope, tag=None, q=ref, date_from=None, date_to=None, limit=5, offset=0))
        if found:
            return found[0]
    raise _not_found("Trip", repr(ref))


async def _find_place(
    services: TravelServices, ref: str, kind: str | None = None, city: str | None = None, country: str | None = None,
    create: bool = False,
) -> PlaceRead:
    """A place by id or exact (case-insensitive) name, narrowed by city; created when `create` and none matches."""
    if _is_id(ref):
        place = await services.places.get_place(int(ref))
        if place is None:
            raise _not_found("Place", ref)
        return place
    candidates = await services.places.get_places(
        PlaceFilters(q=ref, kind=None, city=city, country=None, tag=None, min_grade=None, status=None, no_trip=False, limit=50, offset=0)
    )
    exact = [p for p in candidates if p.name.lower() == ref.lower()]
    if exact:
        return exact[0]
    if not create:
        raise _not_found("Place", repr(ref))
    data = build_model(PlaceCreate, kind=kind or "other", name=ref, city=city, country=country)
    return await services.places.create_place(data)


# ---- summaries ---------------------------------------------------------------

def _trip_summary(trip: TripRead) -> dict[str, Any]:
    return {
        "id": trip.id, "name": trip.name, "start_date": trip.start_date.isoformat(), "end_date": trip.end_date.isoformat(),
        "status": trip.status, "travelers": trip.travelers, "tags": trip.tags,
    }


def _leg_summary(leg: LegRead) -> dict[str, Any]:
    return {
        "id": leg.id, "mode": leg.mode, "from": leg.origin, "to": leg.destination,
        "departs": leg.departs_local.isoformat(timespec="minutes"), "departs_tz": leg.departs_tz,
        "arrives": leg.arrives_local.isoformat(timespec="minutes"), "arrives_tz": leg.arrives_tz,
        "carrier": leg.carrier, "number": leg.number, "booking_ref": leg.booking_ref, "seat": leg.seat, "notes": leg.notes,
    }


def _stay_summary(stay: StayRead) -> dict[str, Any]:
    return {
        "id": stay.id, "place_id": stay.place_id, "place": stay.place.name, "city": stay.place.city,
        "check_in": stay.check_in_local.isoformat(timespec="minutes"), "check_out": stay.check_out_local.isoformat(timespec="minutes"),
        "timezone": stay.timezone, "booking_ref": stay.booking_ref, "grade": stay.grade, "notes": stay.notes,
    }


def _visit_summary(visit: VisitRead) -> dict[str, Any]:
    return {
        "id": visit.id, "place_id": visit.place_id, "place": visit.place.name, "city": visit.place.city,
        "trip_id": visit.trip_id, "status": visit.status,
        "date": visit.visit_date.isoformat() if visit.visit_date else None,
        "time": visit.visit_time.isoformat(timespec="minutes") if visit.visit_time else None,
        "grade": visit.grade, "notes": visit.notes,
    }


def _place_summary(place: PlaceRead) -> dict[str, Any]:
    return {
        "id": place.id, "kind": place.kind, "name": place.name, "city": place.city, "country": place.country,
        "grade": place.grade, "grade_count": place.grade_count, "tags": place.tags, "notes": place.notes,
        "maps_link": place.maps_link,
    }


# ---- dispatch ------------------------------------------------------------------

async def handle_travel(cmd_type: str, command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    logger.debug("handle_travel: %s.%s args_keys=%s", cmd_type, command, list(arguments.keys()))
    handlers = {
        "travel_trip": _trip, "travel_leg": _leg, "travel_stay": _stay, "travel_place": _place, "travel_visit": _visit,
    }
    handler = handlers.get(cmd_type)
    if handler is None:
        raise _bad_request(f"Unknown travel command group: {cmd_type}")
    try:
        return await handler(command, arguments, services)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (TravelConflictError, PlaceInUseError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or "Conflict")
    except (TransferNotLinkableError, ValueError) as exc:
        raise _bad_request(str(exc))


async def _link(kind: str, arguments: dict[str, Any], services: TravelServices, unlink: bool) -> Any:
    entity_id, transaction_id = require_int(arguments, "id"), require_int(arguments, "transaction_id")
    if unlink:
        if not await services.links.unlink(kind, entity_id, transaction_id):
            raise _bad_request("That transaction is not linked")
        return {"message": f"Transaction {transaction_id} unlinked from {kind[:-1]} {entity_id}"}
    linked = await services.links.link(kind, entity_id, transaction_id)
    return {"message": f"Transaction {transaction_id} linked to {kind[:-1]} {entity_id}", "cost": linked.cost.model_dump(mode="json")}


async def _trip(command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    if command == "list":
        status_filter = _text(arguments, "status") or "current"
        limit = optional_int(arguments, "limit", 20)
        tags = parse_tags(arguments.get("tag"))
        if status_filter not in TRIP_STATUS_FILTERS:
            raise _bad_request(f"status must be one of {', '.join(TRIP_STATUS_FILTERS)}, got {status_filter!r}")
        filters = TripFilters(
            status=status_filter, tag=tags or None, q=_text(arguments, "q"), date_from=None, date_to=None,
            city=_text(arguments, "city"), country=_text(arguments, "country"), limit=limit, offset=0,
        )
        trips = await services.trips.get_trips(filters)
        return {"count": len(trips), "trips": [_trip_summary(t) for t in trips]}

    if command == "get":
        ref = _text(arguments, "trip")
        if not ref:
            raise _bad_request("trip is required")
        trip = await _find_trip(services, ref)
        detail = await services.trips.get_trip_detail(trip.id, include_all_visits=_flag(arguments, "all_visits"))
        costs = await services.links.get_trip_costs(trip.id)
        return {
            **_trip_summary(detail),
            "preferences": detail.preferences, "notes": detail.notes, "finance_tags": detail.default_tag_names,
            "checklist_note_id": detail.checklist_note_id,
            "legs": [_leg_summary(leg) for leg in detail.legs],
            "stays": [_stay_summary(s) for s in detail.stays],
            "visits": [_visit_summary(v) for v in detail.visits],
            "hidden_visits": detail.hidden_visit_count,
            "leave_home_at": detail.leave_home_at.isoformat() if detail.leave_home_at else None,
            "warnings": [w.message for w in detail.warnings],
            "cost": costs.total.model_dump(mode="json") if costs else None,
        }

    if command == "add":
        name = _text(arguments, "name")
        data = build_model(
            TripCreate,
            name=name, start_date=_date(_text(arguments, "start"), "start"), end_date=_date(_text(arguments, "end"), "end"),
            travelers=_text(arguments, "travelers"), preferences=_text(arguments, "preferences"),
            notes=_text(arguments, "notes"), default_tag_names=_text(arguments, "finance_tags"),
            checklist_note_id=parse_int(arguments.get("checklist_note"), "checklist_note"), tags=parse_tags(arguments.get("tags")),
        )
        trip = await services.trips.create_trip(data)
        return {"id": trip.id, "message": f"Trip '{trip.name}' created for {trip.start_date} to {trip.end_date}"}

    if command == "update":
        trip_id = require_int(arguments, "id")
        fields = _present(arguments, ("name", "travelers", "preferences", "notes"))
        if "start" in arguments:
            fields["start_date"] = _date(_text(arguments, "start"), "start")
        if "end" in arguments:
            fields["end_date"] = _date(_text(arguments, "end"), "end")
        if "finance_tags" in arguments:
            fields["default_tag_names"] = _text(arguments, "finance_tags")
        if "checklist_note" in arguments:
            fields["checklist_note_id"] = parse_int(arguments.get("checklist_note"), "checklist_note")
        if "tags" in arguments:
            fields["tags"] = parse_tags(arguments.get("tags"))
        if not fields:
            raise _bad_request("Nothing to update")
        trip = await services.trips.update_trip(trip_id, build_model(TripUpdate, **fields))
        if trip is None:
            raise _not_found("Trip", trip_id)
        return {"id": trip.id, "message": f"Trip '{trip.name}' updated"}

    if command == "delete":
        trip_id = require_int(arguments, "id")
        if not await services.trips.delete_trip(trip_id):
            raise _not_found("Trip", trip_id)
        return {"message": f"Trip {trip_id} deleted"}

    if command == "costs":
        trip_id = require_int(arguments, "id")
        costs = await services.links.get_trip_costs(trip_id)
        if costs is None:
            raise _not_found("Trip", trip_id)
        return costs.model_dump(mode="json")

    if command == "recap":
        ref = _text(arguments, "trip")
        if not ref:
            raise _bad_request("trip is required")
        trip = await _find_trip(services, ref)
        recap = await services.recap.get_recap(trip.id)
        if recap is None:
            raise _not_found("Trip", trip.id)
        return recap.model_dump(mode="json")

    if command == "today":
        ref = _text(arguments, "trip")
        if ref:
            trip = await _find_trip(services, ref)
        else:
            ongoing = await services.trips.get_trips(
                TripFilters(status="ongoing", tag=None, q=None, date_from=None, date_to=None, limit=1, offset=0)
            )
            if not ongoing:
                raise _not_found("Trip", "(no ongoing trip)")
            trip = ongoing[0]
        today = await services.trips.get_today(trip.id)
        if today is None:
            raise _not_found("Trip", trip.id)
        return today.model_dump(mode="json")

    if command == "apply_tags":
        trip_id = require_int(arguments, "id")
        names, added = await services.default_tags.apply_to_existing(trip_id)
        if not names:
            return {"message": "The trip has no finance tags set", "tags": [], "added": 0}
        return {"message": f"{added} tag(s) added to expenses within the trip", "tags": names, "added": added}

    raise _bad_request(f"Unknown trip command: {command}")


async def _leg(command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    if command in ("link", "unlink"):
        return await _link("legs", arguments, services, unlink=command == "unlink")

    fields = _present(arguments, (
        "origin", "destination", "origin_code", "destination_code", "carrier", "number", "booking_ref", "booking_url",
        "seat", "notes", "departs_tz", "arrives_tz",
    ))
    if "departs" in arguments:
        fields["departs_at"] = _text(arguments, "departs")
    if "arrives" in arguments:
        fields["arrives_at"] = _text(arguments, "arrives")

    if command == "add":
        trip_id = require_int(arguments, "trip_id")
        data = build_model(LegCreate, trip_id=trip_id, mode=_text(arguments, "mode"), **fields)
        leg = await services.legs.create_leg(data)
        return {"id": leg.id, "message": f"Leg {leg.origin} to {leg.destination} added to trip {trip_id}"}

    if command == "update":
        leg_id = require_int(arguments, "id")
        if "mode" in arguments:
            fields["mode"] = _text(arguments, "mode")
        if not fields:
            raise _bad_request("Nothing to update")
        leg = await services.legs.update_leg(leg_id, build_model(LegUpdate, **fields))
        if leg is None:
            raise _not_found("Leg", leg_id)
        return {"id": leg.id, "message": f"Leg {leg.id} updated"}

    if command == "delete":
        leg_id = require_int(arguments, "id")
        if not await services.legs.delete_leg(leg_id):
            raise _not_found("Leg", leg_id)
        return {"message": f"Leg {leg_id} deleted"}

    raise _bad_request(f"Unknown leg command: {command}")


async def _stay(command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    if command in ("link", "unlink"):
        return await _link("stays", arguments, services, unlink=command == "unlink")

    fields = _present(arguments, ("booking_ref", "booking_url", "notes"))
    if "check_in" in arguments:
        fields["check_in_at"] = _text(arguments, "check_in")
    if "check_out" in arguments:
        fields["check_out_at"] = _text(arguments, "check_out")
    if "tz" in arguments:
        fields["timezone"] = _text(arguments, "tz")
    if "grade" in arguments:
        fields["grade"] = parse_int(arguments.get("grade"), "grade")
    if "trip" in arguments:
        fields["trip_id"] = parse_int(arguments.get("trip"), "trip")

    place_ref, hotel = _text(arguments, "place"), _text(arguments, "hotel")
    if place_ref or hotel:
        place = await _find_place(
            services, place_ref or hotel, kind="hotel", city=_text(arguments, "city"), country=_text(arguments, "country"),
            create=bool(hotel and not place_ref),
        )
        fields["place_id"] = place.id
        if hotel and _text(arguments, "maps_url") and not place.maps_url:
            await services.places.update_place(place.id, PlaceUpdate(maps_url=_text(arguments, "maps_url")))

    if command == "add":
        if "trip_id" not in fields and _text(arguments, "trip_id"):
            fields["trip_id"] = require_int(arguments, "trip_id")
        stay = await services.stays.create_stay(build_model(StayCreate, **fields))
        return {"id": stay.id, "message": f"Stay at {stay.place.name} added"}

    if command == "update":
        stay_id = require_int(arguments, "id")
        if not fields:
            raise _bad_request("Nothing to update")
        stay = await services.stays.update_stay(stay_id, build_model(StayUpdate, **fields))
        if stay is None:
            raise _not_found("Stay", stay_id)
        return {"id": stay.id, "message": f"Stay {stay.id} updated"}

    if command == "delete":
        stay_id = require_int(arguments, "id")
        if not await services.stays.delete_stay(stay_id):
            raise _not_found("Stay", stay_id)
        return {"message": f"Stay {stay_id} deleted"}

    raise _bad_request(f"Unknown stay command: {command}")


async def _place(command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    fields = _present(arguments, ("kind", "city", "country", "maps_url", "address", "notes"))
    for key in ("lat", "lng"):
        if key in arguments:
            fields[key] = _float(_text(arguments, key), key)
    if "tags" in arguments:
        fields["tags"] = parse_tags(arguments.get("tags"))

    if command == "add":
        place = await services.places.create_place(build_model(PlaceCreate, name=_text(arguments, "name"), **{
            "kind": "other", **{k: v for k, v in fields.items() if v is not None},
        }))
        return {"id": place.id, "message": f"Place '{place.name}' added"}

    if command == "list":
        filters = PlaceFilters(
            q=_text(arguments, "q"), kind=_text(arguments, "kind"), city=_text(arguments, "city"),
            country=_text(arguments, "country"), tag=parse_tags(arguments.get("tag")) or None,
            min_grade=parse_int(arguments.get("min_grade"), "min_grade"), ungraded=_flag(arguments, "ungraded"),
            status=_text(arguments, "status"),
            no_trip=_flag(arguments, "no_trip"), limit=optional_int(arguments, "limit", 20),
            offset=optional_int(arguments, "offset", 0),
        )
        places = await services.places.get_places(filters)
        return {"count": len(places), "places": [_place_summary(p) for p in places]}

    if command == "get":
        ref = _text(arguments, "place")
        if not ref:
            raise _bad_request("place is required")
        place = await _find_place(services, ref)
        detail = await services.places.get_place_detail(place.id)
        costs = await services.links.get_place_costs(place.id)
        return {
            **_place_summary(detail),
            "address": detail.address,
            "visits": [_visit_summary(v) for v in detail.visits],
            "stays": [_stay_summary(s) for s in detail.stays],
            "lifetime_cost": costs.total.model_dump(mode="json") if costs else None,
        }

    if command == "update":
        place_id = require_int(arguments, "id")
        if "name" in arguments:
            fields["name"] = _text(arguments, "name")
        if not fields:
            raise _bad_request("Nothing to update")
        place = await services.places.update_place(place_id, build_model(PlaceUpdate, **fields))
        if place is None:
            raise _not_found("Place", place_id)
        return {"id": place.id, "message": f"Place '{place.name}' updated"}

    if command == "delete":
        place_id = require_int(arguments, "id")
        if not await services.places.delete_place(place_id):
            raise _not_found("Place", place_id)
        return {"message": f"Place {place_id} deleted"}

    raise _bad_request(f"Unknown place command: {command}")


def _visit_changes(arguments: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = _present(arguments, ("notes", "status"))
    if "date" in arguments:
        changes["visit_date"] = _date(_text(arguments, "date"), "date")
    if "time" in arguments:
        changes["visit_time"] = _time(_text(arguments, "time"), "time")
    if "grade" in arguments:
        changes["grade"] = parse_int(arguments.get("grade"), "grade")
    if "trip" in arguments:
        changes["trip_id"] = parse_int(arguments.get("trip"), "trip")
    return changes


async def _visit(command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    if command in ("link", "unlink"):
        return await _link("visits", arguments, services, unlink=command == "unlink")

    if command == "add":
        ref = _text(arguments, "place")
        if not ref:
            raise _bad_request("place is required")
        place = await _find_place(
            services, ref, kind=_text(arguments, "kind"), city=_text(arguments, "city"),
            country=_text(arguments, "country"), create=True,
        )
        changes = {k: v for k, v in _visit_changes(arguments).items() if v is not None}
        visit = await services.visits.create_visit(build_model(VisitCreate, place_id=place.id, **changes))
        return {"id": visit.id, "message": f"Visit to {place.name} added ({visit.status})"}

    if command == "list":
        trip_ref = _text(arguments, "trip")
        place_ref = _text(arguments, "place")
        filters = VisitFilters(
            trip_id=(await _find_trip(services, trip_ref)).id if trip_ref else None,
            place_id=(await _find_place(services, place_ref)).id if place_ref else None,
            status=_text(arguments, "status"), date_from=_date(_text(arguments, "date_from"), "from"),
            date_to=_date(_text(arguments, "date_to"), "to"), no_trip=_flag(arguments, "no_trip"),
            limit=optional_int(arguments, "limit", 30), offset=optional_int(arguments, "offset", 0),
        )
        visits = await services.visits.get_visits(filters)
        return {"count": len(visits), "visits": [_visit_summary(v) for v in visits]}

    if command == "update":
        visit_id = require_int(arguments, "id")
        changes = _visit_changes(arguments)
        if "place" in arguments:
            ref = _text(arguments, "place")
            if not ref:
                raise _bad_request("place cannot be empty")
            changes["place_id"] = (await _find_place(services, ref)).id
        if not changes:
            raise _bad_request("Nothing to update")
        visit = await services.visits.update_visit(visit_id, build_model(VisitUpdate, **changes))
        if visit is None:
            raise _not_found("Visit", visit_id)
        return {"id": visit.id, "message": f"Visit {visit.id} updated"}

    if command in ("visited", "missed"):
        visit_id = require_int(arguments, "id")
        changes = {"status": command}
        if command == "visited":
            changes.update({k: v for k, v in _visit_changes(arguments).items() if k in ("grade", "notes", "visit_date")})
        else:
            changes.update({k: v for k, v in _visit_changes(arguments).items() if k == "notes"})
        visit = await services.visits.update_visit(visit_id, build_model(VisitUpdate, **changes))
        if visit is None:
            raise _not_found("Visit", visit_id)
        grade = f", graded {visit.grade}/5" if visit.grade else ""
        return {"id": visit.id, "message": f"Visit to {visit.place.name} marked {visit.status}{grade}"}

    if command == "delete":
        visit_id = require_int(arguments, "id")
        if not await services.visits.delete_visit(visit_id):
            raise _not_found("Visit", visit_id)
        return {"message": f"Visit {visit_id} deleted"}

    raise _bad_request(f"Unknown visit command: {command}")
