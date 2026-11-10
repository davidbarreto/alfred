from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CalendarCandidate(BaseModel):
    """A calendar event inside a trip's dates, ready to be turned into a leg or a stay.

    Times are the event's wall time in `timezone` (its own zone, else the portal's), so a form can
    prefill them as they are and the user corrects whatever the event does not say."""

    event_id: int
    title: str
    location: str | None
    description: str | None
    all_day: bool
    timezone: str
    start_local: datetime
    end_local: datetime
    imported_as: Literal["leg", "stay"] | None = None
    imported_id: int | None = None
