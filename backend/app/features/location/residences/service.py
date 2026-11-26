import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.repository import CityRepository
from app.features.location.errors import LocationConflictError, LocationNotFoundError, LocationValidationError
from app.features.location.places.repository import PlaceRepository
from app.features.location.residences.periods import overlaps
from app.features.location.residences.repository import ResidenceRepository
from app.features.location.residences.schemas import (
    ResidenceCreate,
    ResidenceFilters,
    ResidenceRead,
    ResidenceUpdate,
    check_period,
)
from app.features.location.residences.tables import Residence
from app.shared.utils.timezone import local_today

logger = logging.getLogger(__name__)

# Fields a PATCH may set to null (the others ignore a null).
_NULLABLE = ("from_date", "to_date", "notes")


def _label(residence: Residence) -> str:
    start = residence.from_date.isoformat() if residence.from_date else "birth"
    end = residence.to_date.isoformat() if residence.to_date else "now"
    return f"{residence.city.name} ({start} to {end})"


class ResidenceService:
    """Places lived: periods in a city, at most one open and none overlapping, at most one birth row."""

    def __init__(self, session: AsyncSession):
        self._repo = ResidenceRepository(session)
        self._cities = CityRepository(session)
        self._places = PlaceRepository(session)

    async def list_residences(self, filters: ResidenceFilters) -> list[ResidenceRead]:
        rows = await self._repo.get_page(filters.limit, filters.offset)
        logger.debug("Residences listed: count=%d", len(rows))
        return [ResidenceRead.model_validate(r) for r in rows]

    async def get_residence(self, residence_id: int) -> ResidenceRead | None:
        found = await self._repo.get(residence_id)
        return ResidenceRead.model_validate(found) if found else None

    async def _check(self, candidate: Residence, residence_id: int | None = None) -> None:
        """409 when the row would be a second birth row, a second open row or overlap another period."""
        others = [r for r in await self._repo.get_all() if r.id != residence_id]
        if candidate.born and any(r.born for r in others):
            raise LocationConflictError("Another row is already the birthplace")
        if candidate.to_date is None and any(r.to_date is None for r in others):
            raise LocationConflictError("Another row is still open (still living there): give it an end date first")
        clash = next((r for r in others if overlaps(candidate, r)), None)
        if clash is not None:
            raise LocationConflictError(f"The period overlaps {_label(clash)}")

    async def _city(self, city_id: int):
        city = await self._cities.get_city(city_id)
        if city is None:
            raise LocationNotFoundError(f"City {city_id} not found")
        return city

    async def create_residence(self, data: ResidenceCreate) -> ResidenceRead:
        await self._city(data.city_id)
        residence = Residence(**data.model_dump())
        await self._check(residence)
        await self._repo.add(residence)
        await self._repo.commit()
        await self._repo.refresh(residence)
        logger.info("Residence created: id=%d city_id=%d born=%s", residence.id, residence.city_id, residence.born)
        return ResidenceRead.model_validate(residence)

    async def update_residence(self, residence_id: int, data: ResidenceUpdate) -> ResidenceRead | None:
        residence = await self._repo.get(residence_id)
        if residence is None:
            return None
        sent = data.model_dump(exclude_unset=True)
        changes = {k: v for k, v in sent.items() if v is not None or k in _NULLABLE}
        if "city_id" in changes:
            await self._city(changes["city_id"])
        merged = {f: changes.get(f, getattr(residence, f)) for f in ("from_date", "to_date", "born")}
        try:
            check_period(merged["from_date"], merged["to_date"], merged["born"])
        except ValueError as exc:
            raise LocationValidationError(str(exc)) from exc
        await self._check(Residence(**merged), residence_id)
        for field, value in changes.items():
            setattr(residence, field, value)
        await self._repo.commit()
        await self._repo.refresh(residence)
        logger.info("Residence updated: id=%d fields=%s", residence_id, list(changes.keys()))
        return ResidenceRead.model_validate(residence)

    async def delete_residence(self, residence_id: int) -> bool:
        residence = await self._repo.get(residence_id)
        if residence is None:
            return False
        await self._repo.delete(residence)
        logger.info("Residence deleted: id=%d", residence_id)
        return True

    async def follow_home(self) -> ResidenceRead:
        """The one-click fix when the open row is not the Home place's city: close it today and open one in Home's city
        from today (an open row that starts today or later just moves to Home's city)."""
        home = await self._places.get_home()
        if home is None:
            raise LocationConflictError("There is no Home place")
        rows = await self._repo.get_all()
        current = next((r for r in rows if r.to_date is None), None)
        if current is not None and current.city_id == home.city_id:
            raise LocationConflictError("The open row is already the Home place's city")
        today = local_today()
        if current is not None and current.from_date is not None and current.from_date >= today:
            current.city_id = home.city_id
            target = current
        else:
            if current is not None:
                current.to_date = today
            target = Residence(city_id=home.city_id, from_date=today, born=False)
            clash = next((r for r in rows if r is not current and overlaps(target, r)), None)
            if clash is not None:
                raise LocationConflictError(f"Today is inside {_label(clash)}")
            await self._repo.add(target)
        await self._repo.commit()
        await self._repo.refresh(target)
        logger.info("Residence follows Home: id=%d city_id=%d closed_id=%s", target.id, target.city_id,
                    current.id if current is not None and current is not target else None)
        return ResidenceRead.model_validate(target)
