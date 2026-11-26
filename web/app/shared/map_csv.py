"""The CSV that Google My Maps imports (it geocodes the Address column): trip pins and a city's or country's places."""
import csv
import io
from collections.abc import Iterable, Sequence

from fastapi.responses import Response


def map_csv_response(header: Sequence[str], rows: Iterable[Sequence[str]], filename: str) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def place_address(place: dict) -> str:
    """What My Maps geocodes: "lat,lng" when the place has coordinates, else its address or name, city and country."""
    if place.get("latitude") is not None and place.get("longitude") is not None:
        return f"{place['latitude']},{place['longitude']}"
    city = place.get("city") or {}
    if place.get("address"):
        return ", ".join(p for p in (place["name"], place["address"], city.get("name")) if p)
    return ", ".join(p for p in (place["name"], city.get("name"), (city.get("country") or {}).get("name")) if p)


def place_rows(places: Iterable[dict]) -> list[list[str]]:
    """Name, Address, Category (the kind), Description (the notes) per place."""
    return [[p["name"], place_address(p), p["kind"].replace("_", " "), p.get("notes") or ""] for p in places]
