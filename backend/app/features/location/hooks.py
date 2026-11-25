from collections.abc import Awaitable, Callable
from typing import Protocol

from app.features.location.cities.tables import City

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
