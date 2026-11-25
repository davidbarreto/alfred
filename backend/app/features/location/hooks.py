from collections.abc import Awaitable, Callable
from typing import Protocol

from app.features.location.cities.tables import City
from app.features.location.places.tables import Place

AfterDelete = Callable[[], Awaitable[None]]


class LocationHooks(Protocol):
    """What the domains built on `location` do when its cities and countries change.

    `location` never imports those domains: `dependencies.py` passes their implementation in.
    """

    async def city_created(self, city: City) -> None:
        """Called inside the creating transaction, before the commit."""

    async def city_in_use(self, city: City) -> str | None:
        """Why the city can't be deleted, or None when nothing holds it."""

    async def before_delete(self, *, city_id: int | None = None, country_id: int | None = None) -> AfterDelete:
        """Called before a city or country is deleted; returns what to run once the delete has committed."""


class PlaceHooks(Protocol):
    """What a domain that uses places (organizer's everyday role, travel's trip role) does when one changes.

    `dependencies.py` passes one per domain; `location` never imports them.
    """

    async def place_saved(self, place: Place) -> None:
        """Called after a create or update has committed."""

    async def place_in_use(self, place: Place) -> str | None:
        """Why the place can't be deleted ("2 travel times: ..."), or None when this domain holds nothing."""

    async def before_place_delete(self, place_id: int) -> AfterDelete:
        """Called before the place is deleted; returns what to run once the delete has committed."""
