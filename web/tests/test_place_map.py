"""The Places map: the world page, the map data proxy, the city and country My Maps CSVs, the world.json build."""
import csv
import importlib.util
import io
from pathlib import Path

import httpx

from app.routes.place_map import map_data, world_stats
from app.shared.location_kinds import KINDS, map_group
from app.shared.map_csv import place_address, place_rows

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_world_map.py"


def _load_build_script():
    spec = importlib.util.spec_from_file_location("build_world_map", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _map(**kw):
    return {
        "countries": [{"id": 2, "name": "Examplia", "code": "EX", "city_count": 2},
                      {"id": 3, "name": "Nocodia", "code": None, "city_count": 1}],
        "cities": [{"id": 4, "name": "Alpha", "country_id": 2, "latitude": 38.7, "longitude": -9.1, "home": True}],
        "places": [{"id": 9, "name": "Cafe Example", "kind": "cafe", "city_id": 4, "city_name": "Alpha",
                    "latitude": 38.71, "longitude": -9.14, "maps_url": None, "maps_link": "https://maps.example/x"}],
        "cities_without_coordinates": 0, "places_without_coordinates": 2, **kw,
    }


def _place(id=1, name="Cafe Example", kind="cafe", latitude=None, address=None, notes=None):
    return {"id": id, "name": name, "kind": kind, "latitude": latitude, "longitude": None if latitude is None else 1.5,
            "address": address, "notes": notes,
            "city": {"id": 4, "name": "Alpha", "country": {"id": 2, "name": "Examplia", "code": "EX"}}}


class TestHelpers:
    def test_map_data_adds_icon_and_group(self):
        place = map_data(_map())["places"][0]
        assert place["icon"] == "ti-coffee" and place["group"] == "food"

    def test_every_kind_has_a_group(self):
        assert {map_group(k) for k in KINDS} == {"home", "stay", "food", "sight", "everyday"}
        assert map_group("supermarket") == "everyday" and map_group(None) == "everyday"

    def test_world_stats(self):
        assert world_stats(_map()["countries"]) == {"countries": 2, "cities": 3, "share": 1}
        assert world_stats([])["share"] == 0

    def test_place_address(self):
        assert place_address(_place(latitude=38.7)) == "38.7,1.5"
        assert place_address(_place(address="1 Example Street")) == "Cafe Example, 1 Example Street, Alpha"
        assert place_address(_place()) == "Cafe Example, Alpha, Examplia"

    def test_place_rows(self):
        assert place_rows([_place(kind="variety_store", notes="Open late")]) == [
            ["Cafe Example", "Cafe Example, Alpha, Examplia", "variety store", "Open late"]]


class TestMapPage:
    def test_counters_countries_and_not_on_the_map(self, client, mock_api):
        mock_api["get"].return_value = _map()
        html = client.get("/places/map").text
        assert 'aria-current="page">Map' in html
        assert 'data-map-data="/places/map/data"' in html and "leaflet@" not in html
        assert "cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js" in html
        assert 'href="/places/countries/2"' in html and "Not on the map" in html
        assert "2 places without coordinates" in html
        assert 'data-map-toggle="cities"' in html and 'data-map-toggle="places"' in html

    def test_unavailable(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        html = client.get("/places/map").text
        assert "The map is unavailable right now." in html and "places-map.js" not in html

    def test_tabs_on_other_places_pages_link_the_map(self, client, mock_api):
        mock_api["get"].return_value = []
        assert 'href="/places/map"' in client.get("/places/countries").text


class TestMapData:
    def test_proxies_one_scope_and_enriches(self, client, mock_api):
        mock_api["get"].return_value = _map()
        resp = client.get("/places/map/data?city_id=4&country_id=2")
        assert resp.status_code == 200 and resp.json()["places"][0]["group"] == "food"
        assert mock_api["get"].await_args.kwargs["params"] == {"city_id": "4"}

    def test_world_has_no_params(self, client, mock_api):
        mock_api["get"].return_value = _map()
        client.get("/places/map/data?city_id=x")
        assert mock_api["get"].await_args.kwargs["params"] is None

    def test_backend_down_is_502(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        assert client.get("/places/map/data").status_code == 502


class TestCsv:
    def _rows(self, resp):
        return list(csv.reader(io.StringIO(resp.text)))

    def test_city_csv(self, client, mock_api):
        async def get(path, params=None):
            if path == "/location/cities/4":
                return {"id": 4, "name": "Alpha"}
            assert path == "/location/places" and params["city_id"] == 4 and params["active"] == "true"
            return [_place(latitude=38.7)]
        mock_api["get"].side_effect = get
        resp = client.get("/places/cities/4/map.csv")
        assert resp.headers["content-type"].startswith("text/csv")
        assert 'filename="city-4-map.csv"' in resp.headers["content-disposition"]
        assert self._rows(resp) == [["Name", "Address", "Category", "Description"], ["Cafe Example", "38.7,1.5", "cafe", ""]]

    def test_country_csv_filters_by_country(self, client, mock_api):
        async def get(path, params=None):
            if path == "/location/countries/2":
                return {"id": 2, "name": "Examplia"}
            assert params["country_id"] == 2
            return []
        mock_api["get"].side_effect = get
        resp = client.get("/places/countries/2/map.csv")
        assert self._rows(resp) == [["Name", "Address", "Category", "Description"]]

    def test_unknown_city_redirects(self, client, mock_api):
        mock_api["get"].side_effect = httpx.HTTPStatusError("404", request=None, response=httpx.Response(404))
        resp = client.get("/places/cities/99/map.csv", follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/places/cities"


class TestBuildWorldMap:
    def _square(self, x, y, size=1.0):
        return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]

    def test_codes_rounding_and_dropped_features(self):
        build = _load_build_script()
        source = {"type": "FeatureCollection", "features": [
            {"properties": {"ISO_A2": "-99", "ISO_A2_EH": "FR", "NAME": "France"},
             "geometry": {"type": "Polygon", "coordinates": [self._square(2.123456, 46.987654)]}},
            {"properties": {"ISO_A2": "EX", "NAME": "Examplia"},
             "geometry": {"type": "MultiPolygon", "coordinates": [
                 [self._square(10, 10)], [self._square(20, 20, size=0.001)]]}},
            {"properties": {"ISO_A2": "-99", "ISO_A2_EH": "-99", "NAME": "Disputed"},
             "geometry": {"type": "Polygon", "coordinates": [self._square(0, 0)]}},
        ]}
        world = build.build(source)
        assert [f["properties"] for f in world["features"]] == [{"code": "EX", "name": "Examplia"},
                                                                {"code": "FR", "name": "France"}]
        examplia, france = world["features"]
        # The tiny island collapses below four points and is dropped; one polygon left.
        assert examplia["geometry"]["type"] == "Polygon"
        assert france["geometry"]["coordinates"][0][0] == [2.12, 46.99]

    def test_vendored_file_is_keyed_by_code(self):
        import json
        world = json.loads((Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "world.json").read_text())
        codes = {f["properties"]["code"] for f in world["features"]}
        assert {"PT", "FR", "NO", "BR"} <= codes and all(len(c) == 2 for c in codes)
