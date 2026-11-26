"""Cities and countries in the Places section, their covers, and travel's read-only city and country tables."""
import httpx
import pytest

from app.routes.place_geo import cities_filters, mosaic, sort_cards
from app.routes.travel import location_list_params

NOW = "2026-11-01T00:00:00Z"


def _country(id=2, name="Examplia", code="EX", **kw):
    return {"id": id, "name": name, "code": code, "default_tag_names": None, "has_cover": False, "cover_credit": None,
            "cover_source_url": None, "photos_url": f"https://photos.google.com/search/{name}", "created_at": NOW,
            "updated_at": NOW, **kw}


def _city(id=4, name="Alpha", country=None, **kw):
    return {"id": id, "name": name, "country": country or {"id": 2, "name": "Examplia", "code": "EX"},
            "default_tag_names": None, "latitude": None, "longitude": None, "has_cover": False, "cover_credit": None,
            "cover_source_url": None, "photos_url": f"https://photos.google.com/search/{name}", "created_at": NOW,
            "updated_at": NOW, **kw}


def _costs(linked="80.00", tagged="20.00", count=3):
    def cost(total, n):
        return {"total_eur": total, "transaction_count": n, "unconverted_count": 0}
    return {"linked": cost(linked, 2), "tagged": cost(tagged, count - 2), "overall": cost("100.00", count)}


def _trips(n, album_every=0):
    return [{"id": i, "name": f"Trip {i}", "start_date": "2026-03-01", "end_date": "2026-03-04",
             "photo_album_url": "https://photos.app.goo.gl/x" if album_every and i % album_every == 0 else None,
             "photo_album_label": "Google Photos" if album_every and i % album_every == 0 else None} for i in range(1, n + 1)]


def _travel_city(**kw):
    return {**_city(), "home": False, "grade": 4.5, "grade_count": 2, "place_count": 7, "places": [], "trips": _trips(7),
            "days": 12, "last_visit": "2026-03-01", "costs": _costs(), **kw}


def _travel_country(**kw):
    return {**_country(), "grade": 3.5, "grade_count": 2, "costs": _costs(), "days": 20, "last_visit": "2026-03-01",
            "cities": [{"id": i, "name": f"City {i}", "place_count": i, "grade": None} for i in range(1, 8)],
            "trips": _trips(1), **kw}


def _place(id, name="Cafe Example", kind="cafe"):
    return {"id": id, "name": name, "kind": kind, "city": _city()}


def _route(mock_api, routes):
    async def get(path, params=None):
        key = path if path in routes else next((p for p in sorted(routes, key=len, reverse=True) if path.startswith(p)), None)
        if key is None:
            raise AssertionError(f"unexpected GET {path} {params}")
        value = routes[key]
        if callable(value):
            value = value(params or {})
        if isinstance(value, Exception):
            raise value
        return value
    mock_api["get"].side_effect = get


def _home(city_id):
    return lambda params: [{"id": 29, "kind": "home", "city": _city(id=city_id)}] if params.get("kind") == "home" else [
        _place(i) for i in range(1, 9)]


class TestHelpers:
    def test_filters_fall_back(self):
        assert cities_filters({"sort": "grade", "country_id": "x", "q": " a "}) == {"q": "a", "country_id": "", "sort": "name"}

    def test_sort_cards(self):
        cards = [{"item": {"name": "beta"}, "travel": {"trips": 1, "last_visit": "2026-01-01"}},
                 {"item": {"name": "Alpha"}, "travel": None},
                 {"item": {"name": "Gamma"}, "travel": {"trips": 3, "last_visit": "2025-05-01"}}]
        assert [c["item"]["name"] for c in sort_cards(cards, "name")] == ["Alpha", "beta", "Gamma"]
        assert [c["item"]["name"] for c in sort_cards(cards, "trips")] == ["Gamma", "beta", "Alpha"]
        assert [c["item"]["name"] for c in sort_cards(cards, "last_visit")] == ["beta", "Gamma", "Alpha"]

    def test_mosaic_takes_four_covers_by_name(self):
        cities = [{"id": i, "name": n, "has_cover": c} for i, n, c in
                  [(1, "e", True), (2, "a", True), (3, "b", False), (4, "c", True), (5, "d", True), (6, "f", True)]]
        assert mosaic(cities) == [2, 4, 5, 1]

    def test_location_list_params(self):
        assert location_list_params({"sort": "spend", "desc": "1", "offset": "25"}) == {"sort": "spend", "desc": True, "offset": 25}
        assert location_list_params({"sort": "x", "offset": "-3"}) == {"sort": "name", "desc": False, "offset": 0}


class TestCitiesList:
    def test_cards_with_cover_home_badge_and_travel_line(self, client, mock_api):
        _route(mock_api, {
            "/location/cities": [_city(4, "Alpha", has_cover=True), _city(5, "Home Town")],
            "/travel/cities": [{"id": 4, "name": "Alpha", "trips": 3, "days": 12, "last_visit": "2026-03-01"}],
            "/location/places": _home(5), "/location/countries": [_country()],
        })
        html = client.get("/places/cities").text
        assert 'href="/places/cities/4"' in html and 'src="/places/cities/4/cover?v=' in html
        assert "3 trips · 12 days · last Mar 2026" in html
        assert html.count("ti-home") >= 1 and "8 places" in html
        assert 'aria-current="page">Cities' in html and "Add city" in html

    def test_partial_pages_and_sorts(self, client, mock_api):
        cities = [_city(i, f"City {i:02d}") for i in range(1, 30)]
        _route(mock_api, {"/location/cities": cities, "/travel/cities": [], "/location/places": []})
        html = client.get("/places/cities/list?sort=trips&offset=24").text
        assert 'href="/places/cities/25"' in html and 'href="/places/cities/1"' not in html
        assert "Previous" in html and "Next" not in html and "sort=trips" in html

    def test_country_filter_goes_to_the_api(self, client, mock_api):
        seen = {}

        def cities(params):
            seen.update(params)
            return []
        _route(mock_api, {"/location/cities": cities, "/travel/cities": [], "/location/places": [], "/location/countries": []})
        assert "No city matches" in client.get("/places/cities?country_id=2&q=al").text
        assert seen == {"country_id": "2", "q": "al"}

    def test_unavailable(self, client, mock_api):
        _route(mock_api, {"/location/cities": httpx.ConnectError("down"), "/travel/cities": [], "/location/places": [],
                          "/location/countries": []})
        assert "Cities are unavailable" in client.get("/places/cities").text


class TestCityPage:
    def _routes(self, mock_api, **kw):
        routes = {
            "/location/cities/4": _city(has_cover=True, cover_credit="Photo: A. Author, CC BY-SA 4.0, via Wikimedia Commons",
                                        cover_source_url="https://commons.wikimedia.org/wiki/File:A.jpg", latitude=38.7, longitude=-9.1,
                                        default_tag_names="alpha"),
            "/travel/cities/4/links": [], "/travel/cities/4": _travel_city(trips=_trips(7, album_every=1)),
            "/location/countries": [_country()], "/location/places": _home(99),
        }
        routes.update(kw)
        _route(mock_api, routes)

    def test_hero_actions_stats_and_cards(self, client, mock_api):
        self._routes(mock_api)
        html = client.get("/places/cities/4").text
        assert 'id="city-hero"' in html and 'src="/places/cities/4/cover?v=' in html
        assert "Photo: A. Author, CC BY-SA 4.0" in html and 'href="https://commons.wikimedia.org/wiki/File:A.jpg"' in html
        assert 'href="/places/countries/2"' in html and 'href="https://photos.google.com/search/Alpha"' in html
        assert "Find photo (Wikipedia)" in html and "Remove cover" in html
        # the Map card: fitted to the city, its CSV, place rows that pulse their pin
        assert 'data-map-data="/places/map/data?city_id=4" data-fit="city"' in html
        assert 'href="/places/cities/4/map.csv"' in html and 'data-map-place="1"' in html and "Food and drink" in html
        # stat-row: trips, days, places, grade, spend
        assert ">7<" in html and ">12<" in html and ">8<" in html and "4.5" in html and "100.00 €" in html
        # every list card is capped at 5
        assert html.count('href="/places/') >= 5 and 'href="/places?view=all&city_id=4"' in html and "See all 8 places" in html
        assert 'href="/places/cities/4/trips"' in html and "See all 7 trips" in html
        assert 'href="/places/cities/4/albums"' in html and "See all 7 albums" in html
        assert 'data-owner-kind="city" data-owner-id="4"' in html and "38.7, -9.1" in html
        assert "scope=city&id=4&part=tagged" in html

    def test_home_city_puts_places_first_and_hides_an_empty_trips_card(self, client, mock_api):
        self._routes(mock_api, **{"/location/places": _home(4), "/travel/cities/4": _travel_city(trips=[], days=0)})
        html = client.get("/places/cities/4").text
        assert 'id="city-home"' in html and 'id="city-trips"' not in html and 'id="city-places"' in html

    def test_without_travel_the_page_still_renders(self, client, mock_api):
        self._routes(mock_api, **{"/travel/cities/4": httpx.ConnectError("down"), "/location/places": []})
        html = client.get("/places/cities/4").text
        assert "Alpha" in html and 'id="location-spend"' not in html and "No places here yet" in html

    def test_unknown_city_is_404(self, client, mock_api):
        self._routes(mock_api, **{"/location/cities/9": None, "/travel/cities/9": None, "/travel/cities/9/links": []})
        response = client.get("/places/cities/9")
        assert response.status_code == 404 and "does not exist" in response.text

    def test_links_and_albums_pages(self, client, mock_api):
        self._routes(mock_api)
        assert 'data-owner-kind="city" data-owner-id="4"' in client.get("/places/cities/4/links").text
        albums = client.get("/places/cities/4/albums").text
        assert albums.count('href="https://photos.app.goo.gl/x"') == 7

    def test_trips_redirect_to_the_filtered_travel_list(self, client, mock_api):
        self._routes(mock_api)
        response = client.get("/places/cities/4/trips", follow_redirects=False)
        assert response.status_code == 302 and response.headers["location"] == "/travel?status=all&city=Alpha"


class TestCountries:
    def test_list_with_mosaic_and_flag_placeholder(self, client, mock_api):
        _route(mock_api, {
            "/location/countries": [_country(), _country(3, "Otherland", "OL"), _country(5, "Coverland", None, has_cover=True)],
            "/location/cities": [_city(4, "Alpha", has_cover=True), _city(6, "Beta")],
            "/travel/countries": [{"id": 2, "trips": 3, "days": 20}],
        })
        html = client.get("/places/countries").text
        assert "2 cities · 3 trips · 20 days" in html and "cover-mosaic-1" in html and 'src="/places/cities/4/cover"' in html
        assert 'src="/places/countries/5/cover?v=' in html and "🇴🇱" in html
        assert 'aria-current="page">Countries' in html

    def test_search(self, client, mock_api):
        _route(mock_api, {"/location/countries": [_country(), _country(3, "Otherland")], "/location/cities": [], "/travel/countries": []})
        html = client.get("/places/countries?q=other").text
        assert 'href="/places/countries/3"' in html and 'href="/places/countries/2"' not in html

    def test_country_page(self, client, mock_api):
        cities = [_city(i, f"City {i}", has_cover=i < 3) for i in range(1, 8)]
        _route(mock_api, {"/location/countries/2": _country(), "/travel/countries/2": _travel_country(),
                          "/location/cities": cities, "/travel/countries/2/links": []})
        html = client.get("/places/countries/2").text
        assert 'id="country-hero"' in html and "cover-mosaic-2" in html
        assert 'href="/places/cities/5"' in html and 'href="/places/cities/6"' not in html
        assert 'href="/places/cities?country_id=2"' in html and "See all 7 cities" in html
        assert 'data-owner-kind="country" data-owner-id="2"' in html and "3.5/5" in html
        assert "Find photo" not in html and "Upload cover" in html and 'name="code" value="EX"' in html
        assert 'data-map-data="/places/map/data?country_id=2" data-fit="country"' in html
        assert 'href="/places/countries/2/map.csv"' in html

    def test_unknown_country_is_404(self, client, mock_api):
        _route(mock_api, {"/location/countries/9": None, "/travel/countries/9": None, "/location/cities": [],
                          "/travel/countries/9/links": []})
        assert client.get("/places/countries/9").status_code == 404


class TestWritesAndCovers:
    def test_edits_and_deletes_go_to_location(self, client, mock_api):
        mock_api["patch"].return_value = {"id": 4}
        assert client.patch("/places/cities/4", json={"name": "B", "latitude": None, "longitude": None}).status_code == 200
        mock_api["patch"].assert_awaited_with("/location/cities/4", json={"name": "B", "latitude": None, "longitude": None})
        assert client.patch("/places/countries/2", json={"code": "EX"}).status_code == 200
        mock_api["patch"].assert_awaited_with("/location/countries/2", json={"code": "EX"})
        mock_api["delete"].return_value = None
        assert client.delete("/places/cities/4").status_code == 200
        mock_api["delete"].assert_awaited_with("/location/cities/4")
        assert client.delete("/places/countries/2").status_code == 200

    def test_a_conflict_is_relayed(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/x")
        mock_api["delete"].side_effect = httpx.HTTPStatusError("x", request=request, response=httpx.Response(
            409, request=request, json={"detail": "Alpha is the home city (the Home place is there)"}))
        response = client.delete("/places/cities/4")
        assert response.status_code == 409 and "home city" in response.json()["error"]

    def test_cover_image_is_proxied(self, client, mock_api):
        mock_api["get_bytes"].return_value = (b"\x89PNG", "image/png")
        response = client.get("/places/cities/4/cover")
        assert response.status_code == 200 and response.content == b"\x89PNG" and response.headers["content-type"] == "image/png"
        mock_api["get_bytes"].assert_awaited_with("/location/cities/4/cover")
        request = httpx.Request("GET", "http://api/x")
        mock_api["get_bytes"].side_effect = httpx.HTTPStatusError("x", request=request, response=httpx.Response(404, request=request))
        assert client.get("/places/countries/2/cover").status_code == 404

    def test_upload_and_url_are_sent_as_multipart(self, client, mock_api):
        mock_api["put_multipart"].return_value = {"id": 4, "has_cover": True}
        assert client.put("/places/cities/4/cover", files={"file": ("a.png", b"\x89PNG", "image/png")}).status_code == 200
        args = mock_api["put_multipart"].await_args
        assert args.args == ("/location/cities/4/cover",) and args.kwargs["files"]["file"][1] == b"\x89PNG"
        assert client.put("/places/countries/2/cover", data={"url": " https://example.com/a.jpg "}).status_code == 200
        assert mock_api["put_multipart"].await_args.kwargs == {"data": {"url": "https://example.com/a.jpg"}}

    def test_nothing_to_upload_is_422(self, client, mock_api):
        response = client.put("/places/cities/4/cover", data={"url": " "})
        assert response.status_code == 422 and "Choose an image" in response.json()["error"]
        mock_api["put_multipart"].assert_not_awaited()

    def test_find_and_remove(self, client, mock_api):
        mock_api["post"].return_value = {"id": 4}
        assert client.post("/places/cities/4/cover/find").status_code == 200
        mock_api["post"].assert_awaited_with("/location/cities/4/cover/find", timeout=30.0)
        mock_api["delete"].return_value = None
        assert client.delete("/places/countries/2/cover").status_code == 200
        mock_api["delete"].assert_awaited_with("/location/countries/2/cover")


class TestTravelTables:
    def test_cities_table_links_to_places_and_sorts(self, client, mock_api):
        seen = {}

        def rows(params):
            seen.update(params)
            return [{"id": 4, "name": "Alpha", "country": {"id": 2, "name": "Examplia", "code": "EX"}, "trips": 3, "days": 12,
                     "spend_eur": "100.00", "last_visit": "2026-03-01", "photos_url": "https://photos.google.com/search/Alpha"}]
        _route(mock_api, {"/travel/cities": rows})
        html = client.get("/travel/cities?sort=spend&desc=1").text
        assert seen == {"sort": "spend", "desc": "true", "limit": 26, "offset": 0}
        assert 'href="/places/cities/4"' in html and "100.00 €" in html and "Mar 2026" in html
        assert 'href="/travel/cities?sort=spend"' in html and 'href="https://photos.google.com/search/Alpha"' in html
        assert 'id="new-city"' not in html and 'id="edit-open"' not in html

    def test_countries_table_and_pagination(self, client, mock_api):
        rows = [{"id": i, "name": f"Country {i}", "code": None, "cities": 2, "trips": 1, "days": 3, "spend_eur": "0.00",
                 "last_visit": None, "photos_url": "x"} for i in range(26)]
        _route(mock_api, {"/travel/countries": rows})
        html = client.get("/travel/countries").text
        assert 'href="/places/countries/0"' in html and 'href="/places/countries/25"' not in html and "Next" in html

    @pytest.mark.parametrize("old, new", [
        ("/travel/cities/4", "/places/cities/4"), ("/travel/cities/4/trips", "/places/cities/4/trips"),
        ("/travel/cities/4/links", "/places/cities/4/links"), ("/travel/countries/2", "/places/countries/2"),
        ("/travel/countries/2/cities", "/places/countries/2"), ("/travel/countries/2/trips", "/places/countries/2/trips"),
    ])
    def test_old_detail_pages_redirect(self, client, mock_api, old, new):
        response = client.get(old, follow_redirects=False)
        assert response.status_code == 301 and response.headers["location"] == new

    def test_link_proxies_stay(self, client, mock_api):
        mock_api["post"].return_value = {"id": 1}
        assert client.post("/travel/cities/4/links", json={"url": "https://example.com"}).status_code == 200
        mock_api["post"].assert_awaited_with("/travel/cities/4/links", json={"url": "https://example.com"})
        assert client.post("/travel/countries/2/links", json={"url": "https://example.com"}).status_code == 200

    def test_charges_back_link_goes_to_the_places_page(self, client, mock_api):
        _route(mock_api, {"/travel/cities/4/charges": {"transactions": [], "cost": None}})
        assert 'href="/places/cities/4"' in client.get("/travel/charges?scope=city&id=4&part=linked&name=Alpha").text


class TestTripAlbum:
    def test_trip_page_has_the_photos_button_and_the_field(self, client, mock_api):
        from tests.test_travel import _detail, _route as travel_route
        travel_route(mock_api, {"/travel/trips/1/costs": None, "/travel/trips/1": _detail(
            photo_album_url="https://photos.app.goo.gl/abc", photo_album_label="Google Photos"), "/travel/places": []})
        html = client.get("/travel/1").text
        assert 'id="trip-photos" href="https://photos.app.goo.gl/abc"' in html and "Google Photos" in html
        assert 'name="photo_album_url" type="url" value="https://photos.app.goo.gl/abc"' in html
