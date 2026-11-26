"""City and country covers, Wikipedia lookup, image fetching, city geocoding and enrichment (all I/O mocked)."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import dependencies as deps
from app.features.location.cities.enrichment import CityEnricher
from app.features.location.cities.schemas import CityRead, CityUpdate
from app.features.location.cities.service import CityResolver, CityService
from app.features.location.countries.schemas import CountryRead
from app.features.location.covers import CoverNotFoundError, CoverService, cover_titles
from app.features.location.errors import LocationValidationError
from app.integrations.http.images import MAX_IMAGE_BYTES, HttpImageFetcher, sniff_image_type
from app.integrations.open_meteo.geocoder import OpenMeteoCityGeocoder, pick
from app.integrations.wikipedia.client import WikipediaClient, credit_text, file_name
from app.main import app
from app.shared.protocols.media import CoverPhoto, FetchedImage, GeocodedCity

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def _country(id=1, name="Examplia", code=None, cover_path=None):
    return SimpleNamespace(
        id=id, name=name, code=code, default_tag_names=None, cover_path=cover_path, cover_credit=None,
        cover_source_url=None, created_at=NOW, updated_at=NOW,
    )


def _city(id=1, name="Alpha", country=None, cover_path=None, latitude=None):
    country = country or _country()
    return SimpleNamespace(
        id=id, name=name, country_id=country.id, country=country, default_tag_names=None, latitude=latitude,
        longitude=None if latitude is None else 1.0, cover_path=cover_path, cover_credit=None, cover_source_url=None,
        created_at=NOW, updated_at=NOW,
    )


def _apply(owner, changes):
    for key, value in changes.items():
        setattr(owner, key, value)


def _repos():
    cities, countries = AsyncMock(), AsyncMock()
    cities.update.side_effect = _apply
    countries.update.side_effect = _apply
    countries.get_other_country_by_code.return_value = None
    return cities, countries


def _photo(data=JPEG, content_type="image/jpeg"):
    return CoverPhoto(image=FetchedImage(data, content_type), credit="Photo: A. Author, CC BY-SA 4.0, via Wikimedia Commons",
                      source_url="https://commons.wikimedia.org/wiki/File:Alpha.jpg")


def _cover_service(photo=None, fetched=None):
    storage, photos, images = AsyncMock(), AsyncMock(), AsyncMock()
    photos.find.return_value = photo
    images.fetch.return_value = fetched
    service = CoverService(AsyncMock(), storage, photos, images)
    service._cities, service._countries = _repos()
    return service, storage, photos, images


class TestSniff:
    @pytest.mark.parametrize("data, expected", [
        (JPEG, "image/jpeg"), (PNG, "image/png"), (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"GIF89a....", "image/gif"), (b"<html>", None), (b"", None),
    ])
    def test_types(self, data, expected):
        assert sniff_image_type(data) == expected


class TestSchemas:
    def test_city_read_hides_the_path_and_says_whether_there_is_a_cover(self):
        read = CityRead.model_validate(_city(name="São Paulo", cover_path="covers/cities/1.jpg"))
        dumped = read.model_dump()
        assert "cover_path" not in dumped and dumped["has_cover"] is True
        assert dumped["photos_url"] == "https://photos.google.com/search/S%C3%A3o%20Paulo"

    def test_country_read_has_the_photos_search_and_no_cover(self):
        dumped = CountryRead.model_validate(_country(name="Examplia")).model_dump()
        assert dumped["has_cover"] is False and dumped["photos_url"].endswith("/search/Examplia")

    def test_coordinates_go_together(self):
        assert CityUpdate(latitude=1.5, longitude=2.5).latitude == 1.5
        assert CityUpdate(latitude=None, longitude=None).model_fields_set == {"latitude", "longitude"}
        with pytest.raises(ValidationError):
            CityUpdate(latitude=1.5)
        with pytest.raises(ValidationError):
            CityUpdate(latitude=1.5, longitude=None)
        with pytest.raises(ValidationError):
            CityUpdate(latitude=91, longitude=0)


class TestCityServiceCoordinatesAndDelete:
    async def test_null_coordinates_clear_them(self):
        service = CityService(AsyncMock(), AsyncMock())
        service._repo, service._country_repo = AsyncMock(), AsyncMock()
        city = _city(latitude=3.0)
        service._repo.get_city.return_value = city
        service._repo.get_city_in_country.return_value = city
        await service.update_city(1, CityUpdate(latitude=None, longitude=None))
        assert service._repo.update.await_args.args[1] == {"latitude": None, "longitude": None}

    async def test_deleting_a_city_deletes_its_cover_file_after_the_commit(self):
        hooks, storage = AsyncMock(), AsyncMock()
        hooks.city_in_use.return_value = None
        hooks.before_delete.return_value = AsyncMock()
        service = CityService(AsyncMock(), hooks, storage=storage)
        service._repo = AsyncMock()
        service._residences = AsyncMock(count_in_city=AsyncMock(return_value=0))
        service._repo.get_city.return_value = _city(cover_path="covers/cities/1.jpg")
        assert await service.delete_city(1) is True
        storage.delete.assert_awaited_once_with("covers/cities/1.jpg")

    async def test_a_city_without_cover_deletes_no_file(self):
        hooks, storage = AsyncMock(), AsyncMock()
        hooks.city_in_use.return_value = None
        hooks.before_delete.return_value = AsyncMock()
        service = CityService(AsyncMock(), hooks, storage=storage)
        service._repo = AsyncMock()
        service._residences = AsyncMock(count_in_city=AsyncMock(return_value=0))
        service._repo.get_city.return_value = _city()
        await service.delete_city(1)
        storage.delete.assert_not_awaited()


class TestResolverSchedulesEnrichment:
    async def test_a_created_city_is_scheduled(self):
        cities, countries = AsyncMock(), AsyncMock()
        cities.get_city_in_country.return_value = None
        cities.create_city.return_value = _city(id=7)
        enricher = MagicMock()
        await CityResolver(cities, countries, AsyncMock(), enricher).resolve_city("Alpha", _country())
        enricher.schedule.assert_called_once_with(7)

    async def test_an_existing_city_is_not(self):
        cities = AsyncMock()
        cities.get_city_in_country.return_value = _city()
        enricher = MagicMock()
        await CityResolver(cities, AsyncMock(), AsyncMock(), enricher).resolve_city("Alpha", _country())
        enricher.schedule.assert_not_called()


class TestCoverService:
    def test_titles_try_city_and_country_first(self):
        assert cover_titles("Valencia", "Spain") == ["Valencia, Spain", "Valencia"]

    async def test_find_stores_the_photo_with_its_credit(self):
        service, storage, photos, _ = _cover_service(photo=_photo())
        city = _city(name="Valencia", country=_country(name="Spain"))
        service._cities.get_city.return_value = city
        read = await service.find_city_cover(1)
        photos.find.assert_awaited_once_with(["Valencia, Spain", "Valencia"])
        storage.save.assert_awaited_once_with(JPEG, "covers/cities/1.jpg")
        assert read.has_cover and read.cover_credit.startswith("Photo: A. Author")
        assert read.cover_source_url == "https://commons.wikimedia.org/wiki/File:Alpha.jpg"

    async def test_find_without_a_photo_is_an_error_and_keeps_the_cover(self):
        service, storage, _, _ = _cover_service(photo=None)
        service._cities.get_city.return_value = _city(cover_path="covers/cities/1.png")
        with pytest.raises(CoverNotFoundError, match="No photo found on Wikipedia for Alpha"):
            await service.find_city_cover(1)
        storage.save.assert_not_awaited()

    async def test_find_unknown_city(self):
        service, _, _, _ = _cover_service()
        service._cities.get_city.return_value = None
        assert await service.find_city_cover(9) is None

    async def test_an_upload_replaces_a_cover_of_another_type_and_drops_the_old_file(self):
        service, storage, _, _ = _cover_service()
        city = _city(cover_path="covers/cities/1.jpg")
        city.cover_credit = "old credit"
        service._cities.get_city.return_value = city
        read = await service.set_city_cover(1, data=PNG)
        storage.save.assert_awaited_once_with(PNG, "covers/cities/1.png")
        storage.delete.assert_awaited_once_with("covers/cities/1.jpg")
        assert read.cover_credit is None and read.has_cover

    async def test_same_type_overwrites_in_place(self):
        service, storage, _, _ = _cover_service()
        service._cities.get_city.return_value = _city(cover_path="covers/cities/1.jpg")
        await service.set_city_cover(1, data=JPEG)
        storage.delete.assert_not_awaited()

    @pytest.mark.parametrize("data, message", [
        (b"<svg/>", "not a JPEG, PNG, WebP or GIF"),
        (JPEG + b"0" * MAX_IMAGE_BYTES, "larger than 5 MB"),
    ])
    async def test_bad_uploads(self, data, message):
        service, storage, _, _ = _cover_service()
        service._cities.get_city.return_value = _city()
        with pytest.raises(LocationValidationError, match=message):
            await service.set_city_cover(1, data=data)
        storage.save.assert_not_awaited()

    async def test_exactly_one_of_file_or_url(self):
        service, _, _, _ = _cover_service()
        service._countries.get_country.return_value = _country()
        with pytest.raises(LocationValidationError, match="exactly one"):
            await service.set_country_cover(1)
        with pytest.raises(LocationValidationError, match="exactly one"):
            await service.set_country_cover(1, data=JPEG, url="https://example.com/a.jpg")

    async def test_a_url_is_fetched_once_and_becomes_the_source(self):
        service, storage, _, images = _cover_service(fetched=FetchedImage(JPEG, "image/jpeg"))
        service._countries.get_country.return_value = _country(id=3)
        read = await service.set_country_cover(3, url=" https://example.com/a.jpg ")
        images.fetch.assert_awaited_once_with("https://example.com/a.jpg")
        storage.save.assert_awaited_once_with(JPEG, "covers/countries/3.jpg")
        assert read.cover_source_url == " https://example.com/a.jpg "

    async def test_a_url_that_does_not_fetch(self):
        service, _, _, _ = _cover_service(fetched=None)
        service._countries.get_country.return_value = _country()
        with pytest.raises(LocationValidationError, match="Could not fetch"):
            await service.set_country_cover(1, url="https://example.com/x")

    async def test_remove_clears_the_columns_and_the_file(self):
        service, storage, _, _ = _cover_service()
        country = _country(cover_path="covers/countries/1.webp")
        service._countries.get_country.return_value = country
        read = await service.remove_country_cover(1)
        assert read.has_cover is False and country.cover_path is None
        storage.delete.assert_awaited_once_with("covers/countries/1.webp")

    async def test_read(self):
        service, storage, _, _ = _cover_service()
        service._cities.get_city.return_value = _city(cover_path="covers/cities/1.png")
        storage.read.return_value = PNG
        assert await service.read_city_cover(1) == FetchedImage(PNG, "image/png")
        service._cities.get_city.return_value = _city()
        assert await service.read_city_cover(1) is None
        service._cities.get_city.return_value = None
        assert await service.read_city_cover(1) is None

    async def test_a_missing_file_reads_as_none(self):
        service, storage, _, _ = _cover_service()
        service._cities.get_city.return_value = _city(cover_path="covers/cities/1.png")
        storage.read.return_value = None
        assert await service.read_city_cover(1) is None


class TestEnricher:
    def _enricher(self, found=None, photo=None):
        geocoder, photos = AsyncMock(), AsyncMock()
        geocoder.geocode.return_value = found
        photos.find.return_value = photo
        return CityEnricher(geocoder, photos, AsyncMock(), AsyncMock()), geocoder, photos

    def _patch_repos(self, monkeypatch):
        cities, countries = _repos()
        monkeypatch.setattr("app.features.location.cities.enrichment.CityRepository", lambda s: cities)
        monkeypatch.setattr("app.features.location.cities.enrichment.CountryRepository", lambda s: countries)
        monkeypatch.setattr("app.features.location.covers.CityRepository", lambda s: cities)
        monkeypatch.setattr("app.features.location.covers.CountryRepository", lambda s: countries)
        return cities, countries

    async def test_fills_coordinates_code_and_cover(self, monkeypatch):
        _, countries = self._patch_repos(monkeypatch)
        enricher, geocoder, _ = self._enricher(GeocodedCity(38.7, -9.1, "EX"), _photo())
        city = _city()
        assert await enricher.enrich(AsyncMock(), city) == ["coordinates", "country code", "cover"]
        geocoder.geocode.assert_awaited_once_with("Alpha", "Examplia", None)
        assert (city.latitude, city.longitude, city.country.code) == (38.7, -9.1, "EX")
        assert city.cover_path == "covers/cities/1.jpg"

    async def test_a_code_another_country_has_is_not_taken(self, monkeypatch):
        _, countries = self._patch_repos(monkeypatch)
        countries.get_other_country_by_code.return_value = _country(id=5, code="EX")
        enricher, _, _ = self._enricher(GeocodedCity(1.0, 2.0, "EX"), None)
        city = _city()
        assert await enricher.enrich(AsyncMock(), city) == ["coordinates"]
        assert city.country.code is None

    async def test_nothing_missing_means_no_calls(self, monkeypatch):
        self._patch_repos(monkeypatch)
        enricher, geocoder, photos = self._enricher()
        city = _city(country=_country(code="EX"), latitude=1.0, cover_path="covers/cities/1.jpg")
        assert await enricher.enrich(AsyncMock(), city) == []
        geocoder.geocode.assert_not_awaited()
        photos.find.assert_not_awaited()

    async def test_covers_can_be_skipped(self, monkeypatch):
        self._patch_repos(monkeypatch)
        enricher, _, photos = self._enricher(None, _photo())
        assert await enricher.enrich(AsyncMock(), _city(), covers=False) == []
        photos.find.assert_not_awaited()

    def test_schedule_without_a_session_factory_does_nothing(self):
        enricher, _, _ = self._enricher()
        enricher.schedule(1)  # no running loop needed: nothing is started

    async def test_later_waits_for_the_commit_then_enriches(self, monkeypatch):
        monkeypatch.setattr("app.features.location.cities.enrichment.asyncio.sleep", AsyncMock())
        cities, _ = self._patch_repos(monkeypatch)
        city = _city(country=_country(code="EX"), latitude=1.0)
        cities.get_city.side_effect = [None, city]
        session = AsyncMock()
        session.__aenter__.return_value = session
        enricher, _, photos = self._enricher(None, _photo())
        enricher._session_factory = lambda: session
        await enricher._enrich_later(1)
        assert cities.get_city.await_count == 2
        photos.find.assert_awaited_once()

    async def test_later_gives_up_and_never_raises(self, monkeypatch):
        monkeypatch.setattr("app.features.location.cities.enrichment.asyncio.sleep", AsyncMock())
        cities, _ = self._patch_repos(monkeypatch)
        cities.get_city.side_effect = RuntimeError("db down")
        session = AsyncMock()
        session.__aenter__.return_value = session
        enricher, _, _ = self._enricher()
        enricher._session_factory = lambda: session
        await enricher._enrich_later(1)


class TestGeocoder:
    def test_pick_prefers_the_named_country(self):
        results = [{"name": "Valencia", "country": "Venezuela"}, {"name": "Valencia", "country": "Spain"}]
        assert pick(results, "spain")["country"] == "Spain"
        assert pick(results, "Atlantis")["country"] == "Venezuela"
        assert pick([], "Spain") is None

    async def test_with_a_code_then_without(self):
        client = AsyncMock()
        client.search.side_effect = [[], [{"latitude": 1.5, "longitude": 2.5, "country": "Examplia", "country_code": "ex"}]]
        found = await OpenMeteoCityGeocoder(client).geocode("Alpha", "Examplia", "EX")
        assert found == GeocodedCity(1.5, 2.5, "EX")
        assert client.search.await_args_list[0].kwargs == {"country_code": "EX"}

    async def test_failures_are_none(self):
        client = AsyncMock()
        client.search.side_effect = httpx.ConnectError("down")
        assert await OpenMeteoCityGeocoder(client).geocode("Alpha", "Examplia", None) is None


def _resolve_to(monkeypatch, *ips):
    async def fake_getaddrinfo(host, port, **kwargs):
        return [(2, 1, 6, "", (ip, port)) for ip in ips]

    loop = MagicMock()
    loop.getaddrinfo = fake_getaddrinfo
    monkeypatch.setattr("app.integrations.link_preview.client.asyncio.get_running_loop", lambda: loop)


def _mock_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr("app.integrations.http.images.httpx.AsyncClient", lambda **kw: real(transport=transport, **kw))


class TestImageFetcher:
    async def test_fetches_an_image(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        _mock_transport(monkeypatch, lambda r: httpx.Response(200, content=PNG))
        assert await HttpImageFetcher("ua").fetch("https://example.com/a.png") == FetchedImage(PNG, "image/png")

    async def test_refuses_a_private_host(self, monkeypatch):
        _resolve_to(monkeypatch, "10.0.0.5")
        _mock_transport(monkeypatch, lambda r: httpx.Response(200, content=PNG))
        assert await HttpImageFetcher("ua").fetch("https://internal.example/a.png") is None

    async def test_a_redirect_to_a_private_host_is_refused(self, monkeypatch):
        ips = iter(["93.184.216.34", "127.0.0.1"])

        async def fake_getaddrinfo(host, port, **kwargs):
            return [(2, 1, 6, "", (next(ips), port))]

        loop = MagicMock()
        loop.getaddrinfo = fake_getaddrinfo
        monkeypatch.setattr("app.integrations.link_preview.client.asyncio.get_running_loop", lambda: loop)
        _mock_transport(monkeypatch, lambda r: httpx.Response(302, headers={"location": "http://localhost/x.png"})
                        if r.url.host == "example.com" else httpx.Response(200, content=PNG))
        assert await HttpImageFetcher("ua").fetch("https://example.com/a.png") is None

    async def test_not_an_image(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        _mock_transport(monkeypatch, lambda r: httpx.Response(200, content=b"<html></html>"))
        assert await HttpImageFetcher("ua").fetch("https://example.com/") is None

    async def test_too_large(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        _mock_transport(monkeypatch, lambda r: httpx.Response(200, content=JPEG + b"0" * MAX_IMAGE_BYTES))
        assert await HttpImageFetcher("ua").fetch("https://example.com/big.jpg") is None


_ORIGINAL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Alpha_skyline%2C_2020.jpg"


class TestWikipedia:
    def test_file_name(self):
        assert file_name(_ORIGINAL) == "Alpha_skyline,_2020.jpg"
        assert file_name("https://example.com/a.jpg") is None

    def test_file_name_of_a_thumbnail_is_the_original(self):
        # Some summaries give a thumbnail as the "original": /thumb/<hash>/<File>/<width>px-<File>.
        thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Beta_view%2C_2012.jpg/3840px-Beta_view%2C_2012.jpg"
        assert file_name(thumb) == "Beta_view,_2012.jpg"

    def test_credit_strips_html(self):
        meta = {"Artist": {"value": '<a href="//commons">A.&nbsp;Author</a>'}, "LicenseShortName": {"value": "CC BY-SA 4.0"}}
        assert credit_text(meta) == "Photo: A. Author, CC BY-SA 4.0, via Wikimedia Commons"
        assert credit_text({}) == "Photo via Wikimedia Commons"

    def _client(self, monkeypatch, handler, image=FetchedImage(JPEG, "image/jpeg")):
        transport = httpx.MockTransport(handler)
        real = httpx.AsyncClient
        monkeypatch.setattr("app.integrations.wikipedia.client.httpx.AsyncClient", lambda **kw: real(transport=transport, **kw))
        images = AsyncMock()
        images.fetch.return_value = image
        return WikipediaClient(images), images

    async def test_first_title_with_a_photo_wins(self, monkeypatch):
        seen = []

        def handler(request: httpx.Request):
            seen.append(str(request.url))
            if "/page/summary/Alpha%2C_Examplia" in str(request.url):
                return httpx.Response(404)
            if "/page/summary/Alpha" in str(request.url):
                return httpx.Response(200, json={"type": "standard", "originalimage": {"source": _ORIGINAL}})
            return httpx.Response(200, json={"query": {"pages": [{"imageinfo": [{
                "url": _ORIGINAL, "thumburl": "https://upload.wikimedia.org/thumb/1600px.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Alpha.jpg",
                "extmetadata": {"Artist": {"value": "A. Author"}, "LicenseShortName": {"value": "CC BY 2.0"}},
            }]}]}})

        client, images = self._client(monkeypatch, handler)
        photo = await client.find(["Alpha, Examplia", "Alpha"])
        assert photo.credit == "Photo: A. Author, CC BY 2.0, via Wikimedia Commons"
        assert photo.source_url == "https://commons.wikimedia.org/wiki/File:Alpha.jpg"
        images.fetch.assert_awaited_once_with("https://upload.wikimedia.org/thumb/1600px.jpg")
        assert "titles=File%3AAlpha_skyline%2C_2020.jpg" in seen[-1] and "iiurlwidth=1600" in seen[-1]

    async def test_a_disambiguation_page_is_skipped(self, monkeypatch):
        client, images = self._client(monkeypatch, lambda r: httpx.Response(
            200, json={"type": "disambiguation", "originalimage": {"source": _ORIGINAL}}))
        assert await client.find(["Valencia"]) is None
        images.fetch.assert_not_awaited()

    async def test_errors_are_none(self, monkeypatch):
        client, _ = self._client(monkeypatch, lambda r: httpx.Response(500))
        assert await client.find(["Alpha"]) is None


class TestRoutes:
    @pytest.fixture
    def client(self):
        covers = AsyncMock()
        app.dependency_overrides[deps.get_cover_service] = lambda: covers
        yield TestClient(app), covers
        app.dependency_overrides.clear()

    def _city_read(self):
        return CityRead.model_validate(_city(cover_path="covers/cities/1.jpg"))

    def test_get_a_cover(self, client):
        c, covers = client
        covers.read_city_cover.return_value = FetchedImage(PNG, "image/png")
        response = c.get("/location/cities/1/cover", headers=AUTH)
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        assert response.content == PNG and "max-age" in response.headers["cache-control"]

    def test_no_cover_is_404(self, client):
        c, covers = client
        covers.read_city_cover.return_value = None
        covers.read_country_cover.return_value = None
        assert c.get("/location/cities/1/cover", headers=AUTH).status_code == 404
        assert c.get("/location/countries/1/cover", headers=AUTH).status_code == 404

    def test_upload(self, client):
        c, covers = client
        covers.set_city_cover.return_value = self._city_read()
        response = c.put("/location/cities/1/cover", headers=AUTH, files={"file": ("a.png", PNG, "image/png")})
        assert response.status_code == 200 and response.json()["has_cover"] is True
        assert covers.set_city_cover.await_args.kwargs == {"data": PNG, "url": None}

    def test_url(self, client):
        c, covers = client
        covers.set_country_cover.return_value = CountryRead.model_validate(_country())
        assert c.put("/location/countries/1/cover", headers=AUTH, data={"url": "https://example.com/a.jpg"}).status_code == 200
        assert covers.set_country_cover.await_args.kwargs == {"data": None, "url": "https://example.com/a.jpg"}

    def test_invalid_image_is_422(self, client):
        c, covers = client
        covers.set_city_cover.side_effect = LocationValidationError("The file is not a JPEG, PNG, WebP or GIF image")
        response = c.put("/location/cities/1/cover", headers=AUTH, files={"file": ("a.svg", b"<svg/>", "image/svg+xml")})
        assert response.status_code == 422 and "not a JPEG" in response.json()["detail"]

    def test_find(self, client):
        c, covers = client
        covers.find_city_cover.return_value = self._city_read()
        assert c.post("/location/cities/1/cover/find", headers=AUTH).status_code == 200
        covers.find_city_cover.side_effect = CoverNotFoundError("No photo found on Wikipedia for Alpha")
        response = c.post("/location/cities/1/cover/find", headers=AUTH)
        assert response.status_code == 404 and "No photo" in response.json()["detail"]

    def test_unknown_owner_is_404(self, client):
        c, covers = client
        covers.remove_city_cover.return_value = None
        covers.set_country_cover.return_value = None
        assert c.delete("/location/cities/9/cover", headers=AUTH).status_code == 404
        assert c.put("/location/countries/9/cover", headers=AUTH, data={"url": "https://e.com/a"}).status_code == 404

    def test_auth(self, client):
        c, _ = client
        assert c.get("/location/cities/1/cover").status_code in (401, 403)


class TestMigration103:
    def _module(self):
        path = Path(__file__).parents[1] / "alembic" / "versions" / "103_city_covers_and_coordinates.py"
        spec = importlib.util.spec_from_file_location("migration_103", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
    def test_every_column_added_is_dropped(self, monkeypatch, direction):
        module = self._module()
        op = MagicMock()
        monkeypatch.setattr(module, "op", op)
        module.upgrade()
        added = {(c.args[0], c.args[1].name) for c in op.add_column.call_args_list}
        op.reset_mock()
        module.downgrade()
        dropped = {(c.args[0], c.args[1]) for c in op.drop_column.call_args_list}
        assert added == dropped
        assert ("trips", "photo_album_url") in added and ("cities", "latitude") in added
        assert ("countries", "cover_path") in added


class TestDependencies:
    def test_disabled_integrations_use_null_providers_and_schedule_nothing(self, monkeypatch):
        monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(disable_integrations=True, media_storage_dir="/tmp/x"))
        enricher = deps.get_city_enricher()
        assert enricher._session_factory is None
        assert type(deps.get_cover_photo_provider()).__name__ == "NullCoverPhotoProvider"
        assert type(deps.get_image_fetcher()).__name__ == "NullImageFetcher"

    def test_enabled_integrations_use_wikipedia_and_a_session_factory(self, monkeypatch):
        monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(disable_integrations=False, media_storage_dir="/tmp/x"))
        assert deps.get_city_enricher()._session_factory is not None
        assert isinstance(deps.get_cover_photo_provider(), WikipediaClient)
        assert isinstance(deps.get_image_fetcher(), HttpImageFetcher)

    async def test_null_providers(self):
        from app.integrations.null.media_provider import NullCityGeocoder, NullCoverPhotoProvider, NullImageFetcher
        assert await NullCoverPhotoProvider().find(["A"]) is None
        assert await NullImageFetcher().fetch("https://e.com") is None
        assert await NullCityGeocoder().geocode("A", "B", None) is None
