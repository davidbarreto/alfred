"""Build web/app/static/js/world.json, the country shapes behind the Places map.

Source: Natural Earth's 1:110m Admin 0 countries (public domain, https://www.naturalearthdata.com), as GeoJSON:

    curl -L -o /tmp/ne_110m.geojson \
      https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson
    python web/scripts/build_world_map.py /tmp/ne_110m.geojson

Each feature keeps only `code` (ISO 3166-1 alpha-2, what matches a country in Alfred) and `name`; coordinates are
rounded to two decimals (about 1 km, finer than the 1:110m shapes) and repeated points dropped, which brings the
file to about 100 KB. ISO_A2 is "-99" for a few countries (France, Norway), so ISO_A2_EH is used then; features
with no code at all (disputed areas) are left out. At this scale very small countries (Andorra, Malta, Singapore)
have no shape: their cities still get markers.
"""
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "world.json"
_NO_CODE = "-99"


def country_code(properties: dict) -> str | None:
    for key in ("ISO_A2", "ISO_A2_EH"):
        value = (properties.get(key) or "").strip().upper()
        if len(value) == 2 and value != _NO_CODE:
            return value
    return None


def _ring(points: list) -> list:
    out: list[list[float]] = []
    for lng, lat, *_ in points:
        point = [round(lng, 2), round(lat, 2)]
        if not out or out[-1] != point:
            out.append(point)
    # A ring needs four positions (the first repeated last); a shape too small for that at this precision is noise.
    return out if len(out) >= 4 else []


def simplify(geometry: dict) -> dict | None:
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    elif geometry["type"] == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        return None
    kept = []
    for outer, *holes in polygons:
        # An island too small for the outer ring is dropped with its holes; a tiny hole alone is just dropped.
        shell = _ring(outer)
        if shell:
            kept.append([shell, *(r for r in (_ring(hole) for hole in holes) if r)])
    if not kept:
        return None
    if len(kept) == 1:
        return {"type": "Polygon", "coordinates": kept[0]}
    return {"type": "MultiPolygon", "coordinates": kept}


def build(source: dict) -> dict:
    features = []
    for feature in source["features"]:
        props = feature.get("properties") or {}
        code = country_code(props)
        geometry = simplify(feature["geometry"]) if code and feature.get("geometry") else None
        if geometry is None:
            continue
        features.append({
            "type": "Feature", "properties": {"code": code, "name": props.get("NAME") or props.get("ADMIN") or code},
            "geometry": geometry,
        })
    features.sort(key=lambda f: f["properties"]["code"])
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: build_world_map.py <ne_110m_admin_0_countries.geojson>")
    source = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    world = build(source)
    OUTPUT.write_text(json.dumps(world, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{len(world['features'])} countries -> {OUTPUT} ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
