import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, optional_int, parse_int, parse_tags, require_int
from app.features.location.cities.schemas import CityFilters
from app.features.location.cities.service import CityService
from app.features.location.countries.service import CountryService
from app.features.travel.constants import TRIP_STATUS_FILTERS
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.default_tags import TripDefaultTagService
from app.features.travel.legs.schemas import LegCreate, LegRead, LegUpdate
from app.features.travel.links.schemas import WebLinkCreate, WebLinkRead, WebLinkUpdate
from app.features.travel.links.service import WebLinkService
from app.features.travel.legs.service import LegService
from app.features.travel.recap.service import TripRecapService
from app.features.location.errors import LocationConflictError
from app.features.location.places.service import PlaceService
from app.features.travel.places.schemas import TravelPlaceCreate, TravelPlaceFilters, TravelPlaceRead, TravelPlaceUpdate
from app.features.travel.places.service import TravelPlaceService
from app.features.travel.stays.schemas import StayCreate, StayRead, StayUpdate
from app.features.travel.stays.service import StayService
from app.features.travel.transaction_links.service import TransactionLinkService, TransferNotLinkableError
from app.features.travel.trips.schemas import TripCreate, TripFilters, TripRead, TripUpdate
from app.features.travel.trips.service import TripService
from app.features.travel.visits.schemas import VisitCreate, VisitFilters, VisitRead, VisitUpdate
from app.features.travel.visits.note_log import append_note, pick_note_visit
from app.features.travel.visits.service import VisitService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TravelServices:
    trips: TripService
    legs: LegService
    stays: StayService
    places: TravelPlaceService
    visits: VisitService
    links: TransactionLinkService
    default_tags: TripDefaultTagService
    recap: TripRecapService
    web_links: WebLinkService | None = None
    cities: CityService | None = None
    countries: CountryService | None = None
    # What a place is (deleting it): location's service, which asks organizer and travel what holds the place.
    base_places: PlaceService | None = None


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
) -> TravelPlaceRead:
    """A place by id or exact (case-insensitive) name, narrowed by city; created when `create` and none matches."""
    if _is_id(ref):
        place = await services.places.get_place(int(ref))
        if place is None:
            raise _not_found("Place", ref)
        return place
    candidates = await services.places.get_places(
        TravelPlaceFilters(q=ref, kind=None, city=city, country=None, tag=None, min_grade=None, status=None, no_trip=False, limit=50, offset=0)
    )
    exact = [p for p in candidates if p.name.lower() == ref.lower()]
    if exact:
        return exact[0]
    if not create:
        raise _not_found("Place", repr(ref))
    if not city or not country:
        raise _bad_request(f"Which city and country is {ref} in?")
    data = build_model(TravelPlaceCreate, kind=kind or "other", name=ref, city=city, country=country)
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
        "id": stay.id, "place_id": stay.place_id, "place": stay.place.name, "city": stay.place.city.name,
        "check_in": stay.check_in_local.isoformat(timespec="minutes"), "check_out": stay.check_out_local.isoformat(timespec="minutes"),
        "timezone": stay.timezone, "booking_ref": stay.booking_ref, "grade": stay.grade, "notes": stay.notes,
    }


def _visit_summary(visit: VisitRead) -> dict[str, Any]:
    return {
        "id": visit.id, "place_id": visit.place_id, "place": visit.place.name, "city": visit.place.city.name,
        "trip_id": visit.trip_id, "status": visit.status,
        "date": visit.visit_date.isoformat() if visit.visit_date else None,
        "time": visit.visit_time.isoformat(timespec="minutes") if visit.visit_time else None,
        "grade": visit.grade, "notes": visit.notes,
    }


def _place_summary(place: TravelPlaceRead) -> dict[str, Any]:
    return {
        "id": place.id, "kind": place.kind, "name": place.name, "city": place.city.name, "country": place.city.country.name,
        "grade": place.grade, "grade_count": place.grade_count, "tags": place.tags, "notes": place.notes,
        "maps_link": place.maps_link,
    }


# ---- links -------------------------------------------------------------------

_OWNERS = ("trip", "place", "city", "country")


def _link_summary(link: WebLinkRead) -> dict[str, Any]:
    return {"id": link.id, "url": link.url, "title": link.title, "kind": link.kind, "notes": link.notes}


async def _find_city(services: TravelServices, ref: str, country: str | None) -> int:
    """A city by id, or by exact name (case-insensitive); a name found in several countries is refused, never guessed."""
    if _is_id(ref):
        return int(ref)
    found = await services.cities.get_cities(CityFilters(country_id=None, q=ref))
    matches = [c for c in found if c.name.lower() == ref.lower()]
    if country:
        matches = [c for c in matches if c.country.name.lower() == country.lower()]
    if not matches:
        raise _not_found("City", repr(ref))
    if len(matches) > 1:
        countries = ", ".join(c.country.name for c in matches)
        raise _bad_request(f"{ref} exists in several countries ({countries}): add the country")
    return matches[0].id


async def _find_country(services: TravelServices, ref: str) -> int:
    if _is_id(ref):
        return int(ref)
    matches = [c for c in await services.countries.get_countries() if c.name.lower() == ref.lower()]
    if not matches:
        raise _not_found("Country", repr(ref))
    return matches[0].id


async def _link_owner(arguments: dict[str, Any], services: TravelServices) -> tuple[str, int]:
    """The one owner (trip, place, city or country) a link command is about, by id or name."""
    given = [(kind, _text(arguments, kind)) for kind in _OWNERS if _text(arguments, kind)]
    # A country given next to a city only narrows the city.
    if len(given) == 2 and {k for k, _ in given} == {"city", "country"}:
        given = [g for g in given if g[0] == "city"]
    if len(given) != 1:
        raise _bad_request("Give exactly one of trip, place, city or country (an id or a name)")
    kind, ref = given[0]
    if kind == "trip":
        return kind, (await _find_trip(services, ref)).id
    if kind == "place":
        return kind, (await _find_place(services, ref)).id
    if kind == "city":
        return kind, await _find_city(services, ref, _text(arguments, "country"))
    return kind, await _find_country(services, ref)


async def _web_link(command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    if command == "suggest":
        ref = _text(arguments, "trip")
        if not ref:
            raise _bad_request("trip is required")
        trip = await _find_trip(services, ref)
        detail = await services.trips.get_trip_detail(trip.id)
        cities = [c.city for c in detail.cities if c.role in ("home", "stayed")]
        countries = {c.country.id: c.country for c in cities}
        return {
            "trip": trip.name,
            "cities": [{"id": c.id, "name": c.name, "country": c.country.name,
                        "saved": [link.url for link in await services.web_links.get_city_links(c.id)]} for c in cities],
            "countries": [{"id": c.id, "name": c.name,
                           "saved": [link.url for link in await services.web_links.get_country_links(c.id)]} for c in countries.values()],
        }

    if command == "list":
        kind, owner_id = await _link_owner(arguments, services)
        links = await getattr(services.web_links, f"get_{kind}_links")(owner_id)
        return {"count": len(links), "links": [_link_summary(link) for link in links]}

    if command == "add":
        url = _text(arguments, "url")
        kind, owner_id = await _link_owner(arguments, services)
        data = build_model(WebLinkCreate, url=url, kind=_text(arguments, "kind"), title=_text(arguments, "title"), notes=_text(arguments, "notes"))
        link = await getattr(services.web_links, f"create_{kind}_link")(owner_id, data)
        return {"id": link.id, "message": f"Link saved on {kind} {owner_id}", **_link_summary(link)}

    if command == "update":
        link_id = require_int(arguments, "id")
        fields = _present(arguments, ("url", "kind", "title", "notes"))
        if not fields:
            raise _bad_request("Nothing to update")
        link = await services.web_links.update_link(link_id, build_model(WebLinkUpdate, **fields))
        if link is None:
            raise _not_found("Link", link_id)
        return {"id": link.id, "message": f"Link {link.id} updated", **_link_summary(link)}

    if command == "delete":
        link_id = require_int(arguments, "id")
        if not await services.web_links.delete_link(link_id):
            raise _not_found("Link", link_id)
        return {"message": f"Link {link_id} deleted"}

    raise _bad_request(f"Unknown link command: {command}")


# ---- dispatch ------------------------------------------------------------------

async def handle_travel(cmd_type: str, command: str, arguments: dict[str, Any], services: TravelServices) -> Any:
    logger.debug("handle_travel: %s.%s args_keys=%s", cmd_type, command, list(arguments.keys()))
    handlers = {
        "travel_trip": _trip, "travel_leg": _leg, "travel_stay": _stay, "travel_place": _place, "travel_visit": _visit,
        "travel_link": _web_link,
    }
    handler = handlers.get(cmd_type)
    if handler is None:
        raise _bad_request(f"Unknown travel command group: {cmd_type}")
    try:
        return await handler(command, arguments, services)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (TravelConflictError, LocationConflictError) as exc:
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
            await services.places.update_place(place.id, TravelPlaceUpdate(maps_url=_text(arguments, "maps_url")))

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
    if "lat" in arguments or "lng" in arguments:
        lat, lng = _float(_text(arguments, "lat"), "lat"), _float(_text(arguments, "lng"), "lng")
        if (lat is None) != (lng is None):
            raise _bad_request("Give both --lat and --lng, or neither")
        fields["coordinates"] = None if lat is None else (lat, lng)
    if "tags" in arguments:
        fields["tags"] = parse_tags(arguments.get("tags"))

    if command == "add":
        if not fields.get("city") or not fields.get("country"):
            raise _bad_request(f"Which city and country is {_text(arguments, 'name')} in?")
        place = await services.places.create_place(build_model(TravelPlaceCreate, name=_text(arguments, "name"), **{
            "kind": "other", **{k: v for k, v in fields.items() if v is not None},
        }))
        return {"id": place.id, "message": f"Place '{place.name}' added"}

    if command == "list":
        filters = TravelPlaceFilters(
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
        place = await services.places.update_place(place_id, build_model(TravelPlaceUpdate, **fields))
        if place is None:
            raise _not_found("Place", place_id)
        return {"id": place.id, "message": f"Place '{place.name}' updated"}

    if command == "delete":
        place_id = require_int(arguments, "id")
        if services.base_places is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Place service not available")
        if not await services.base_places.delete(place_id):
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

    if command == "note":
        text = _text(arguments, "text")
        if not text:
            raise _bad_request("text is required")
        ongoing = await services.trips.get_trips(
            TripFilters(status="ongoing", tag=None, q=None, date_from=None, date_to=None, limit=1, offset=0)
        )
        if not ongoing:
            raise _not_found("Trip", "(no ongoing trip)")
        today = await services.trips.get_today(ongoing[0].id)
        detail = await services.trips.get_trip_detail(ongoing[0].id, include_all_visits=True)
        if today is None or detail is None:
            raise _not_found("Trip", ongoing[0].id)
        local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(today.timezone)).replace(tzinfo=None)
        target = pick_note_visit(detail.visits, local_now)
        if target is None:
            return {"message": "No visit has started yet, so the note was not saved. Use update to edit a specific visit."}
        await services.visits.update_visit(target.id, VisitUpdate(notes=append_note(target.notes, local_now, text)))
        return {"id": target.id, "message": f"Note added to the visit to {target.place.name}"}

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
