from app.features.location.errors import LocationNotFoundError
from app.features.location.map.repository import MapRepository
from app.features.location.map.schemas import MapCity, MapCountry, MapFilters, MapPlace, PlacesMap


class MapService:
    """The Places map's data: location only (no grades or everyday flags), active places with coordinates."""

    def __init__(self, repo: MapRepository) -> None:
        self._repo = repo

    async def get_map(self, filters: MapFilters) -> PlacesMap:
        country_id, city_id = filters.country_id, filters.city_id
        if city_id is not None:
            # A city's map still draws its country's shape.
            country_id = await self._repo.city_country_id(city_id)
            if country_id is None:
                raise LocationNotFoundError(f"City {city_id} not found")
        elif country_id is not None and not await self._repo.country_exists(country_id):
            raise LocationNotFoundError(f"Country {country_id} not found")
        home_city_id = await self._repo.home_city_id()
        countries = await self._repo.countries(country_id)
        cities = await self._repo.cities(country_id, city_id)
        places = await self._repo.places(country_id, city_id)
        return PlacesMap(
            countries=[MapCountry(**row) for row in countries],
            cities=[MapCity(**row, home=row["id"] == home_city_id) for row in cities],
            places=[MapPlace(**row) for row in places],
            cities_without_coordinates=await self._repo.cities_without_coordinates(country_id, city_id),
            places_without_coordinates=await self._repo.places_without_coordinates(country_id, city_id),
        )
