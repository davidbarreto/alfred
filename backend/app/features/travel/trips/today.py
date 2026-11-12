"""Pure function: what matters right now on a trip (next step, today's visits). No DB or IO."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.features.travel.trips.schemas import TripDetail
from app.features.travel.trips.timeline import TimelineItem
from app.features.travel.visits.schemas import VisitRead


class TripToday(BaseModel):
    trip_id: int
    trip_name: str
    # The traveler's calendar day: in the zone of the stay covering now, else the home zone.
    date: date
    timezone: str
    next_item: TimelineItem | None = None
    minutes_until_next: int | None = None
    visits: list[VisitRead] = []
    # Planned visits of today that are not marked yet.
    to_mark: int = 0


def _current_zone(trip: TripDetail, now: datetime, home_zone: str) -> str:
    stay = next((s for s in trip.stays if s.check_in_at <= now <= s.check_out_at), None)
    return stay.timezone if stay else home_zone


def build_today(trip: TripDetail, now: datetime, home_zone: str) -> TripToday:
    now = now.astimezone(timezone.utc)
    zone = _current_zone(trip, now, home_zone)
    today = now.astimezone(ZoneInfo(zone)).date()
    upcoming = [i for i in trip.timeline if i.at >= now]
    next_item = min(upcoming, key=lambda i: (i.at, i.ref_id), default=None)
    visits = [v for v in trip.visits if v.visit_date == today]
    return TripToday(
        trip_id=trip.id, trip_name=trip.name, date=today, timezone=zone, next_item=next_item,
        minutes_until_next=int((next_item.at - now).total_seconds() // 60) if next_item else None,
        visits=visits, to_mark=sum(1 for v in visits if v.status == "planned"),
    )
