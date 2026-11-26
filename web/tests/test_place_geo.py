"""Cities and countries in the Places section, their covers, and the redirects from travel's old city and country tables."""
import httpx
import pytest

from app.routes.place_geo import cities_filters, lived_note, mosaic, sort_cards

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
            "nights": 12, "stay_count": 6, "leg_count": 0, "last_visit": "2026-03-01", "costs": _costs(), **kw}


def _travel_country(**kw):
    return {**_country(), "grade": 3.5, "grade_count": 2, "costs": _costs(), "nights": 20, "stay_count": 9, "last_visit": "2026-03-01",
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


# The Countries tab also asks for Places lived and the Home place.
_NO_LIVED = {"/location/residences": [], "/location/places": []}


def _residence(id, city, from_date="2019-03-01", to_date=None, born=False):
    return {"id": id, "city": city, "from_date": from_date, "to_date": to_date, "born": born, "notes": None,
            "current": to_date is None, "created_at": NOW, "updated_at": NOW}


class TestHelpers:
    def test_filters_fall_back(self):
        assert cities_filters({"sort": "grade", "country_id": "x", "q": " a ", "status": "home"}) == {
            "q": "a", "country_id": "", "status": "visited", "sort": "name"}
        assert cities_filters({"status": "passed"})["status"] == "passed"

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

    def test_sort_cards_by_nights(self):
        cards = [{"item": {"name": "Alpha"}, "travel": {"nights": 2}}, {"item": {"name": "Beta"}, "travel": {"nights": 5}},
                 {"item": {"name": "Gamma"}, "travel": None}]
        assert [c["item"]["name"] for c in sort_cards(cards, "nights")] == ["Beta", "Alpha", "Gamma"]
        assert cities_filters({"sort": "nights"})["sort"] == "nights"

    def test_sort_cards_by_spend(self):
        cards = [{"item": {"name": "Alpha"}, "travel": {"spend_eur": "20.00"}},
                 {"item": {"name": "Beta"}, "travel": None},
                 {"item": {"name": "Gamma"}, "travel": {"spend_eur": "100.50"}}]
        assert [c["item"]["name"] for c in sort_cards(cards, "spend")] == ["Gamma", "Alpha", "Beta"]


class TestCitiesList:
    def test_cards_with_cover_home_badge_and_travel_line(self, client, mock_api):
        _route(mock_api, {
            "/location/cities": [_city(4, "Alpha", has_cover=True), _city(5, "Home Town")],
            "/travel/cities": [{"id": 4, "name": "Alpha", "status": "visited", "trips": 3, "nights": 12, "last_visit": "2026-03-01"},
                               {"id": 5, "name": "Home Town", "status": "home", "trips": 0, "nights": 0, "last_visit": None}],
            "/location/places": _home(5), "/location/countries": [_country()],
        })
        html = client.get("/places/cities").text
        assert 'href="/places/cities/4"' in html and 'src="/places/cities/4/cover?v=' in html
        assert "3 trips · 12 nights · last Mar 2026" in html
        assert html.count("ti-home") >= 1 and "8 places" in html
        assert 'aria-current="page">Cities' in html and "Add city" in html

    def test_card_line_shows_spend_and_leaves_out_zero_figures(self, client, mock_api):
        _route(mock_api, {
            "/location/cities": [_city(4, "Alpha"), _city(6, "Beta")],
            "/travel/cities": [{"id": 4, "trips": 3, "nights": 8, "spend_eur": "1240.40", "last_visit": "2026-08-01"},
                               {"id": 6, "trips": 1, "nights": 0, "spend_eur": "0.00", "last_visit": "2026-08-01"}],
            "/location/places": _home(99), "/location/countries": [_country()],
        })
        html = client.get("/places/cities?sort=spend").text
        assert "3 trips · 8 nights · 1,240 € · last Aug 2026" in html and "1 trip · last Aug 2026" in html
        assert html.index('id="city-4"') < html.index('id="city-6"') and '<option value="spend" selected>' in html

    def test_cards_are_a_grid(self, client, mock_api):
        _route(mock_api, {"/location/cities": [_city()], "/travel/cities": [], "/location/places": [], "/location/countries": []})
        assert '<div class="card-grid" style="--card-min: 14rem">' in client.get("/places/cities?status=all").text

    def test_partial_pages_and_sorts(self, client, mock_api):
        cities = [_city(i, f"City {i:02d}") for i in range(1, 30)]
        _route(mock_api, {"/location/cities": cities, "/travel/cities": [], "/location/places": []})
        html = client.get("/places/cities/list?sort=trips&status=all&offset=24").text
        assert 'href="/places/cities/25"' in html and 'href="/places/cities/1"' not in html
        assert "Previous" in html and "Next" not in html and "status=all&amp;sort=trips" in html

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


class TestStatusChips:
    def _travel(self, seen):
        def travel(params):
            seen.append(params.get("status"))
            return [{"id": 4, "status": "planned", "trips": 1, "nights": 0, "last_visit": None}] if params.get("status") != "visited" else []
        return travel

    def test_cities_default_to_visited_and_show_only_what_travel_lists(self, client, mock_api):
        seen = []
        _route(mock_api, {"/location/cities": [_city(4, "Alpha"), _city(6, "Beta")], "/travel/cities": self._travel(seen),
                          "/location/places": [], "/location/countries": []})
        html = client.get("/places/cities").text
        assert seen == ["visited"] and "No city matches" in html
        assert 'data-status="visited"' in html and "Passed through" in html
        assert 'class="px-3 py-1 rounded-full text-xs whitespace-nowrap bg-[#378ADD] text-white" data-status="visited"' in html
        assert 'href="/places/cities?status=planned"' in html and 'href="/places/cities"' in html
        assert '<input type="hidden" name="status" value="visited">' in html

    def test_cities_planned_and_all(self, client, mock_api):
        seen = []
        _route(mock_api, {"/location/cities": [_city(4, "Alpha"), _city(6, "Beta")], "/travel/cities": self._travel(seen),
                          "/location/places": [], "/location/countries": []})
        html = client.get("/places/cities/list?status=planned&q=a").text
        assert 'id="city-4"' in html and 'id="city-6"' not in html and "status=planned" not in html  # one page, no pager
        html = client.get("/places/cities?status=all").text
        assert 'id="city-4"' in html and 'id="city-6"' in html and seen == ["planned", "all"]

    def test_countries_follow_the_chip(self, client, mock_api):
        seen = []
        _route(mock_api, {"/location/countries": [_country(4, "Alphaland"), _country(6, "Betaland")], "/location/cities": [],
                          "/travel/countries": self._travel(seen), **_NO_LIVED})
        html = client.get("/places/countries?status=planned&sort=trips").text
        assert 'id="country-4"' in html and 'id="country-6"' not in html and seen == ["planned"]
        assert 'href="/places/countries?status=passed&amp;sort=trips"' in html and 'href="/places/countries?sort=trips"' in html
        assert '<input type="hidden" name="status" value="planned">' in html


class TestCityPage:
    def _routes(self, mock_api, **kw):
        routes = {
            "/location/cities/4": _city(has_cover=True, cover_credit="Photo: A. Author, CC BY-SA 4.0, via Wikimedia Commons",
                                        cover_source_url="https://commons.wikimedia.org/wiki/File:A.jpg", latitude=38.7, longitude=-9.1,
                                        default_tag_names="alpha"),
            "/travel/cities/4/links": [], "/travel/cities/4/legs": [], "/travel/cities/4": _travel_city(trips=_trips(7, album_every=1)),
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
        # The card opens on the visited pins; the status toggles sit, hidden, under the Show button.
        toggles = html[html.index('id="city-map-toggles"'):html.index('data-map-data=')]
        assert "hidden" in toggles.split(">")[0] and 'data-map-status="visited" checked' in toggles
        assert 'data-map-status="planned">' in toggles and 'aria-controls="city-map-toggles"' in html
        # stat-row: trips, nights, places, grade, spend, each linking to its source
        assert ">7<" in html and ">12<" in html and ">8<" in html and "4.5" in html and "100.00 €" in html
        assert '<a href="/places/cities/4/trips" class="card bg-white hover:shadow-md transition-shadow" id="stat-trips">' in html
        assert '<a href="/places/cities/4/stays" class="card bg-white hover:shadow-md transition-shadow" id="stat-nights">' in html
        assert '<a href="/places?view=all&city_id=4" class="card' in html
        assert '<a href="/places?view=visited&city_id=4&min_grade=1" class="card' in html
        assert '<a href="/travel/charges?scope=city&id=4&part=overall&name=Alpha" class="card' in html
        assert 'id="city-legs"' not in html
        # every list card is capped at 5
        assert html.count('href="/places/') >= 5 and 'href="/places?view=all&city_id=4"' in html and "See all 8 places" in html
        assert 'href="/places/cities/4/trips"' in html and "See all 7 trips" in html
        assert 'href="/places/cities/4/albums"' in html and "See all 7 albums" in html
        assert 'data-owner-kind="city" data-owner-id="4"' in html and "38.7, -9.1" in html
        assert "scope=city&id=4&part=tagged" in html

    def test_zero_nights_still_shows_a_tile_on_a_travel_city(self, client, mock_api):
        self._routes(mock_api, **{"/travel/cities/4": _travel_city(nights=0, stay_count=0)})
        html = client.get("/places/cities/4").text
        assert 'id="stat-nights"><div class="card-body p-4"><p class="text-xs text-gray-400">Nights</p><p class="text-2xl font-semibold text-gray-900 mt-1">0<' in html

    def test_legs_card_caps_at_five_and_links_to_trip_and_page(self, client, mock_api):
        legs = [{"id": i, "trip_id": 2, "trip_name": "Road trip", "mode": "car", "origin": "Hometown", "destination": "Alpha",
                 "origin_city": None, "destination_city": None, "departs_local": "2026-08-21T09:00:00",
                 "arrives_local": "2026-08-21T15:00:00"} for i in range(1, 6)]
        seen = {}

        def leg_rows(params):
            seen.update(params)
            return legs
        self._routes(mock_api, **{"/travel/cities/4/legs": leg_rows, "/travel/cities/4": _travel_city(leg_count=9)})
        html = client.get("/places/cities/4").text
        assert seen == {"limit": 5} and 'id="city-legs"' in html and html.count('id="leg-') == 5
        assert "Hometown → Alpha" in html and "car · 21 Aug 2026" in html and 'href="/travel/2">Road trip' in html
        assert 'href="/places/cities/4/legs"' in html and "See all 9 legs" in html

    def test_home_city_puts_places_first_and_hides_an_empty_trips_card(self, client, mock_api):
        self._routes(mock_api, **{"/location/places": _home(4), "/travel/cities/4": _travel_city(trips=[], nights=0, stay_count=0)})
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


def _stay_row(id, city_id=4, trip_id=2):
    return {"id": id, "trip_id": trip_id, "trip_name": "Road trip" if trip_id else None, "place_id": 30 + id,
            "place_name": f"Hotel {id}", "place_kind": "hotel", "city": {"id": city_id, "name": "Alpha", "country": {"id": 2, "name": "Examplia", "code": "EX"}},
            "check_in_local": "2026-08-23T15:00:00", "check_out_local": "2026-08-26T10:00:00", "nights": 3}


class TestStaysAndLegsPages:
    def test_city_stays_page_links_to_hotel_and_trip_and_pages(self, client, mock_api):
        seen = {}

        def stays(params):
            seen.update(params)
            return [_stay_row(i) for i in range(1, 22)] if params["offset"] == 0 else []
        _route(mock_api, {"/location/cities/4": _city(), "/travel/cities/4/stays": stays, "/travel/cities/4": _travel_city(stay_count=30)})
        html = client.get("/places/cities/4/stays").text
        assert seen == {"limit": 21, "offset": 0} and html.count('id="stay-') == 20 and "Stays in Alpha" in html and ">30<" in html
        assert 'href="/places/31"' in html and 'href="/travel/2">Road trip' in html and "23 Aug 2026 → 26 Aug 2026 · 3 nights" in html
        assert 'hx-get="/places/cities/4/stays/list?offset=20"' in html and 'href="/places/cities/4"' in html
        assert 'href="/places/cities/4">Alpha' not in html  # one city: no city column

    def test_country_stays_show_the_city_and_a_stay_without_trip(self, client, mock_api):
        _route(mock_api, {"/location/countries/2": _country(), "/travel/countries/2/stays": [_stay_row(1, trip_id=None)],
                          "/travel/countries/2": _travel_country()})
        html = client.get("/places/countries/2/stays").text
        assert "Stays in Examplia" in html and 'href="/places/cities/4">Alpha' in html and "No trip" in html

    def test_legs_page_and_partial(self, client, mock_api):
        legs = [{"id": 1, "trip_id": 2, "trip_name": "Road trip", "mode": "flight", "origin": "Hometown", "destination": "Alpha",
                 "origin_city": None, "destination_city": None, "departs_local": "2026-08-21T09:00:00", "arrives_local": "2026-08-21T11:00:00"}]
        _route(mock_api, {"/location/cities/4": _city(), "/travel/cities/4/legs": legs, "/travel/cities/4": _travel_city(leg_count=1)})
        html = client.get("/places/cities/4/legs").text
        assert "Legs to and from Alpha" in html and "flight · 21 Aug 2026" in html
        partial = client.get("/places/cities/4/legs/list?offset=20").text
        assert "<html" not in partial and "Previous" in partial and 'hx-get="/places/cities/4/legs/list?offset=0"' in partial

    def test_unknown_owner_is_404_and_travel_down_says_so(self, client, mock_api):
        _route(mock_api, {"/location/cities/9": httpx.HTTPStatusError("404", request=httpx.Request("GET", "x"), response=httpx.Response(404)),
                          "/travel/cities/9": None, "/travel/cities/9/stays": None})
        assert client.get("/places/cities/9/stays").status_code == 404
        _route(mock_api, {"/location/cities/4": _city(), "/travel/cities/4/stays": httpx.ConnectError("down"),
                          "/travel/cities/4": httpx.ConnectError("down")})
        assert "Travel is unavailable" in client.get("/places/cities/4/stays").text


class TestCountries:
    def test_list_with_mosaic_and_flag_placeholder(self, client, mock_api):
        _route(mock_api, {
            "/location/countries": [_country(), _country(3, "Otherland", "OL"), _country(5, "Coverland", None, has_cover=True)],
            "/location/cities": [_city(4, "Alpha", has_cover=True), _city(6, "Beta")],
            "/travel/countries": [{"id": 2, "trips": 3, "nights": 20}], **_NO_LIVED,
        })
        html = client.get("/places/countries?status=all").text
        assert "2 cities · 3 trips · 20 nights" in html and "cover-mosaic-1" in html and 'src="/places/cities/4/cover"' in html
        assert 'src="/places/countries/5/cover?v=' in html and "🇴🇱" in html
        assert 'aria-current="page">Countries' in html

    def test_country_page_numbers_link_to_their_lists(self, client, mock_api):
        _route(mock_api, {"/location/countries/2": _country(), "/travel/countries/2/links": [], "/travel/countries/2": _travel_country(),
                          "/location/cities": [_city()]})
        html = client.get("/places/countries/2").text
        assert '<a href="/places/cities?country_id=2&status=all" class="card' in html and '<a href="/places/countries/2/trips" class="card' in html
        assert '<a href="/places/countries/2/stays" class="card' in html and ">20<" in html
        assert '<a href="/travel/charges?scope=country&id=2&part=overall&name=Examplia" class="card' in html

    def test_sort_by_spend_keeps_the_sort_when_paging(self, client, mock_api):
        countries = [_country(i, f"Country {i:02d}", None) for i in range(1, 27)]
        _route(mock_api, {"/location/countries": countries, "/location/cities": [],
                          "/travel/countries": [{"id": 26, "trips": 1, "nights": 2, "spend_eur": "50.00", "last_visit": None}],
                          **_NO_LIVED})
        html = client.get("/places/countries?sort=spend&status=all").text
        assert html.index('id="country-26"') < html.index('id="country-1"') and "1 trip · 2 nights · 50 €" in html
        assert 'href="/places/countries?status=all&amp;sort=spend&offset=24"' in html and '<div class="card-grid"' in html

    def test_search(self, client, mock_api):
        _route(mock_api, {"/location/countries": [_country(), _country(3, "Otherland")], "/location/cities": [], "/travel/countries": [],
                          **_NO_LIVED})
        html = client.get("/places/countries?q=other&status=all").text
        assert 'href="/places/countries/3"' in html and 'href="/places/countries/2"' not in html

    def test_country_page(self, client, mock_api):
        cities = [_city(i, f"City {i}", has_cover=i < 3) for i in range(1, 8)]
        _route(mock_api, {"/location/countries/2": _country(), "/travel/countries/2": _travel_country(),
                          "/location/cities": cities, "/travel/countries/2/links": []})
        html = client.get("/places/countries/2").text
        assert 'id="country-hero"' in html and "cover-mosaic-2" in html
        assert 'href="/places/cities/5"' in html and 'href="/places/cities/6"' not in html
        assert 'href="/places/cities?country_id=2&status=all"' in html and "See all 7 cities" in html
        assert 'data-owner-kind="country" data-owner-id="2"' in html and "3.5/5" in html
        assert "Find photo" not in html and "Upload cover" in html and 'name="code" value="EX"' in html
        assert 'data-map-data="/places/map/data?country_id=2" data-fit="country"' in html
        assert 'href="/places/countries/2/map.csv"' in html
        assert 'id="country-map-toggles" hidden' in html

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
    @pytest.mark.parametrize("old, new", [("/travel/cities", "/places/cities"), ("/travel/countries", "/places/countries")])
    def test_old_tables_redirect_to_the_places_tabs(self, client, mock_api, old, new):
        response = client.get(old, follow_redirects=False)
        assert response.status_code == 301 and response.headers["location"] == new
        mock_api["get"].assert_not_awaited()

    def test_travel_header_has_one_places_link(self, client, mock_api):
        mock_api["get"].return_value = []
        html = client.get("/travel").text
        assert 'href="/places"' in html and 'href="/travel/cities"' not in html and 'href="/travel/countries"' not in html

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


class TestPlacesLived:
    def test_note_only_when_the_open_row_is_not_homes_city(self):
        alpha, beta = _city(4, "Alpha"), _city(6, "Beta")
        assert lived_note([], alpha) is None and lived_note([_residence(1, alpha)], None) is None
        assert lived_note([_residence(1, alpha)], alpha) is None
        assert lived_note([_residence(1, beta)], alpha) == {"home": alpha, "current": beta}
        assert lived_note([_residence(1, beta, to_date="2026-01-01")], alpha) == {"home": alpha, "current": None}

    def test_countries_tab_has_the_card_rows_note_and_see_all(self, client, mock_api):
        alpha, beta = _city(4, "Alpha"), _city(6, "Beta", country={"id": 3, "name": "Testland", "code": "TL"})
        rows = [_residence(i, alpha, from_date=f"20{20 - i:02d}-01-01", to_date=f"20{21 - i:02d}-01-01") for i in range(1, 6)]
        rows = [_residence(9, beta, from_date="2021-01-01")] + rows + [_residence(8, beta, None, "2005-03-01", born=True)]
        _route(mock_api, {"/location/countries": [], "/location/cities": [], "/travel/countries": [],
                          "/location/residences": rows, "/location/places": [{"id": 1, "kind": "home", "city": alpha}]})
        html = client.get("/places/countries").text
        assert 'id="places-lived"' in html and 'id="residence-9"' in html and 'id="residence-4"' in html
        assert 'id="residence-5"' not in html and 'id="residence-8"' not in html
        assert 'href="/places/lived"' in html and "See all 7" in html
        assert "The Home place is in Alpha, but Places lived still has you in Beta" in html and "Moved to Alpha today" in html
        assert "Jan 2021 – now" in html and 'id="lived-dialog"' in html and "travel-city-picker.js" in html

    def test_lived_page_lists_every_row(self, client, mock_api):
        alpha = _city(4, "Alpha")
        _route(mock_api, {"/location/residences": [_residence(1, alpha), _residence(2, alpha, None, "2005-03-01", born=True)]})
        html = client.get("/places/lived").text
        assert 'id="residence-1"' in html and 'id="residence-2"' in html and "Birth – Mar 2005" in html and ">Born<" in html
        assert "data-lived-edit=" in html and "&#34;city&#34;" in html

    def test_country_cards_say_living_or_lived_and_born(self, client, mock_api):
        _route(mock_api, {
            "/location/countries": [_country(), _country(3, "Testland", "TL")],
            "/location/cities": [_city(4, "Alpha"), _city(5, "Beta")],
            "/travel/countries": [
                {"id": 2, "status": "home", "trips": 4, "nights": 0, "living": True, "lived_since": "2019-03-01"},
                {"id": 3, "status": "lived", "trips": 3, "trips_since": 2, "nights": 14, "born": True, "lived_until": "2005-03-01"},
            ], **_NO_LIVED,
        })
        html = client.get("/places/countries").text
        assert "Living here since Mar 2019 · 2 cities" in html and "4 trips" not in html
        assert "Lived here until 2005 · 2 trips since · 14 nights" in html and "Born here" in html

    def test_city_card_born_badge_and_lived_line(self, client, mock_api):
        _route(mock_api, {"/location/cities": [_city(4, "Alpha")], "/location/places": [], "/location/countries": [],
                          "/travel/cities": [{"id": 4, "status": "lived", "trips": 1, "trips_since": 0, "nights": 0, "born": True,
                                              "lived_until": "2005-03-01", "last_visit": None}]})
        html = client.get("/places/cities").text
        assert "Lived here until 2005" in html and "data-born" in html and "1 trip" not in html

    def test_city_and_country_heroes(self, client, mock_api):
        TestCityPage()._routes(mock_api, **{"/travel/cities/4": _travel_city(born=True, living=True, lived_since=None)})
        html = client.get("/places/cities/4").text
        assert 'id="city-born"' in html and '<span id="city-lived">Living here since birth</span>' in html
        _route(mock_api, {"/location/countries/2": _country(), "/travel/countries/2/links": [], "/location/cities": [],
                          "/travel/countries/2": _travel_country(lived_until="2005-03-01")})
        html = client.get("/places/countries/2").text
        assert "EX · <span id=\"country-lived\">Lived here until 2005</span>" in html and 'id="country-born"' not in html

    @pytest.mark.parametrize("method, path, backend", [
        ("post", "/places/residences", ("post", "/location/residences")),
        ("patch", "/places/residences/3", ("patch", "/location/residences/3")),
        ("post", "/places/residences/follow-home", ("post", "/location/residences/follow-home")),
    ])
    def test_writes_forward(self, client, mock_api, method, path, backend):
        mock_api[backend[0]].return_value = {"id": 3}
        kwargs = {} if path.endswith("follow-home") else {"json": {"city_id": 4, "from_date": "2019-03-01"}}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 200 and mock_api[backend[0]].await_args.args[0] == backend[1]

    def test_delete_and_conflict(self, client, mock_api):
        mock_api["delete"].return_value = None
        assert client.delete("/places/residences/3").status_code == 200
        request = httpx.Request("POST", "http://api/location/residences")
        mock_api["post"].side_effect = httpx.HTTPStatusError(
            "409", request=request, response=httpx.Response(409, json={"detail": "The period overlaps Alpha"}, request=request))
        response = client.post("/places/residences", json={"city_id": 4})
        assert response.status_code == 409 and response.json()["error"] == "The period overlaps Alpha"
