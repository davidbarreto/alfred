"""One-off: give the cities that existed before phase 6 of the location domain their coordinates, their countries'
missing ISO codes and a Wikipedia cover photo (new cities get them on create, in the background).

For each city, in name order: geocode it with Open-Meteo when it has no coordinates or its country no code, then look
for a cover on Wikipedia ("<City>, <Country>", then "<City>") when it has none. Nothing already set is replaced, so
re-running only fills what is still missing. Only city and country names leave the server.

Dry run by default: prints what each city lacks and touches nothing (no network call either). With --apply it fetches
and writes, and prints what it filled. --no-covers fills only coordinates and codes.

Usage (from backend/, or `$COMPOSE exec -T api python scripts/backfill_city_covers.py [--apply] [--no-covers]`):
    python scripts/backfill_city_covers.py
    python scripts/backfill_city_covers.py --apply
"""
import argparse
import asyncio

import app.main  # noqa: F401 -- registers every mapped table before the first query
from app.db.session import async_session
from app.dependencies import get_city_enricher
from app.features.location.cities.repository import CityRepository
from app.features.location.cities.schemas import CityFilters


def _missing(city, covers: bool) -> list[str]:
    missing = []
    if city.latitude is None:
        missing.append("coordinates")
    if city.country.code is None:
        missing.append("country code")
    if covers and city.cover_path is None:
        missing.append("cover")
    return missing


async def main(apply: bool, covers: bool) -> None:
    enricher = get_city_enricher()
    async with async_session() as session:
        cities = await CityRepository(session).get_cities(CityFilters())
        print(f"{len(cities)} cities")
        for city in cities:
            missing = _missing(city, covers)
            label = f"{city.id:>4}  {city.name}, {city.country.name}"
            if not missing:
                print(f"{label}: complete")
            elif not apply:
                print(f"{label}: lacks {', '.join(missing)}")
            else:
                filled = await enricher.enrich(session, city, covers=covers)
                still = [m for m in missing if m not in filled]
                print(f"{label}: filled {', '.join(filled) or 'nothing'}" + (f"; still lacks {', '.join(still)}" if still else ""))
    if not apply:
        print("Dry run: nothing written. Re-run with --apply to fetch and write.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="fetch and write (default: dry run)")
    parser.add_argument("--no-covers", action="store_true", help="only coordinates and country codes")
    args = parser.parse_args()
    asyncio.run(main(args.apply, not args.no_covers))
