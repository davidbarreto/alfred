from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.links.kind import display_domain, guess_kind
from app.features.travel.links.schemas import WebLinkCreate, WebLinkUpdate
from app.features.travel.links.service import WebLinkService
from app.integrations.link_preview.client import (
    LinkPreview, LinkPreviewClient, UnsafeUrlError, assert_public_url, parse_preview,
)

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


def _link(**kw):
    base = dict(
        id=1, trip_id=1, place_id=None, url="https://example.com/a", kind="website", title="Title", description=None,
        image_url=None, notes=None, created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestGuessKind:
    @pytest.mark.parametrize("url,kind", [
        ("https://www.instagram.com/some_page/", "instagram"),
        ("https://vm.tiktok.com/abc", "tiktok"),
        ("https://www.tiktok.com/@x/video/1", "tiktok"),
        ("https://youtu.be/abc", "video"),
        ("https://www.youtube.com/watch?v=abc", "video"),
        ("https://vimeo.com/1", "video"),
        ("https://maps.app.goo.gl/abc", "map"),
        ("https://www.google.com/maps/d/viewer?mid=1", "map"),
        ("https://www.google.com/search?q=x", "website"),
        ("https://notinstagram.com/x", "website"),
        ("https://visit.example.org/", "website"),
    ])
    def test_by_domain(self, url, kind):
        assert guess_kind(url) == kind

    def test_display_domain_drops_www(self):
        assert display_domain("https://www.example.com/path") == "example.com"


class TestSchemas:
    @pytest.mark.parametrize("url", ["ftp://example.com", "javascript:alert(1)", "example.com", "https://", "   "])
    def test_rejects_non_web_urls(self, url):
        with pytest.raises(ValidationError):
            WebLinkCreate(url=url)

    def test_trims_the_url(self):
        assert WebLinkCreate(url="  https://example.com/x  ").url == "https://example.com/x"

    def test_rejects_an_overlong_url(self):
        with pytest.raises(ValidationError):
            WebLinkCreate(url="https://example.com/" + "a" * 2000)

    def test_update_validates_a_given_url_but_allows_none(self):
        assert WebLinkUpdate().url is None
        with pytest.raises(ValidationError):
            WebLinkUpdate(url="ftp://x.example")

    def test_unknown_kind_is_refused(self):
        with pytest.raises(ValidationError):
            WebLinkCreate(url="https://example.com", kind="podcast")


class TestParsePreview:
    def test_prefers_open_graph_tags(self):
        html = (
            '<html><head><title>Plain title</title>'
            '<meta property="og:title" content="OG title">'
            '<meta property="og:description" content="OG desc">'
            '<meta property="og:image" content="/img/cover.jpg"></head></html>'
        )
        assert parse_preview(html, "https://example.com/page") == LinkPreview(
            "OG title", "OG desc", "https://example.com/img/cover.jpg"
        )

    def test_falls_back_to_title_and_meta_description(self):
        html = '<title>  Visit\n  Example </title><meta name="description" content="About">'
        assert parse_preview(html, "https://example.com") == LinkPreview("Visit Example", "About", None)

    def test_drops_a_non_web_image(self):
        html = '<meta property="og:image" content="data:image/png;base64,AAAA">'
        assert parse_preview(html, "https://example.com").image_url is None

    def test_empty_page(self):
        assert parse_preview("<html></html>", "https://example.com") == LinkPreview(None, None, None)


class TestAssertPublicUrl:
    @pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.18.0.2", "169.254.169.254", "::1"])
    async def test_refuses_private_addresses(self, monkeypatch, ip):
        _resolve_to(monkeypatch, ip)
        with pytest.raises(UnsafeUrlError):
            await assert_public_url("https://internal.example/")

    async def test_refuses_a_host_with_any_private_address(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34", "10.0.0.5")
        with pytest.raises(UnsafeUrlError):
            await assert_public_url("https://mixed.example/")

    async def test_refuses_other_schemes(self):
        with pytest.raises(UnsafeUrlError):
            await assert_public_url("file:///etc/passwd")

    async def test_accepts_a_public_address(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        await assert_public_url("https://example.com/")


def _resolve_to(monkeypatch, *ips):
    async def fake_getaddrinfo(host, port, **kwargs):
        return [(2, 1, 6, "", (ip, port)) for ip in ips]

    loop = MagicMock()
    loop.getaddrinfo = fake_getaddrinfo
    monkeypatch.setattr("app.integrations.link_preview.client.asyncio.get_running_loop", lambda: loop)


def _mock_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr(
        "app.integrations.link_preview.client.httpx.AsyncClient",
        lambda **kw: real(transport=transport, **kw),
    )


class TestLinkPreviewClient:
    async def test_fetches_and_parses(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        _mock_transport(monkeypatch, lambda r: httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, text='<meta property="og:title" content="Hi">'
        ))
        assert (await LinkPreviewClient().fetch("https://example.com/")).title == "Hi"

    async def test_redirect_to_a_private_host_is_refused(self, monkeypatch):
        calls = []

        async def fake_getaddrinfo(host, port, **kwargs):
            calls.append(host)
            return [(2, 1, 6, "", ("10.0.0.5" if host == "internal.example" else "93.184.216.34", port))]

        loop = MagicMock()
        loop.getaddrinfo = fake_getaddrinfo
        monkeypatch.setattr("app.integrations.link_preview.client.asyncio.get_running_loop", lambda: loop)
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://internal.example/admin"})

        _mock_transport(monkeypatch, handler)
        assert await LinkPreviewClient().fetch("https://example.com/") is None
        assert seen == ["https://example.com/"]
        assert calls == ["example.com", "internal.example"]

    async def test_too_many_redirects(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        _mock_transport(monkeypatch, lambda r: httpx.Response(302, headers={"location": "https://example.com/again"}))
        assert await LinkPreviewClient().fetch("https://example.com/") is None

    async def test_non_html_is_skipped(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        _mock_transport(monkeypatch, lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"))
        assert await LinkPreviewClient().fetch("https://example.com/a.pdf") is None

    async def test_http_error_returns_none(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        _mock_transport(monkeypatch, lambda r: httpx.Response(403, text="no"))
        assert await LinkPreviewClient().fetch("https://example.com/") is None

    async def test_a_huge_body_is_cut_off(self, monkeypatch):
        _resolve_to(monkeypatch, "93.184.216.34")
        body = '<meta property="og:title" content="Early">' + "x" * 2_000_000
        _mock_transport(monkeypatch, lambda r: httpx.Response(200, headers={"content-type": "text/html"}, text=body))
        assert (await LinkPreviewClient().fetch("https://example.com/")).title == "Early"

    async def test_unsafe_scheme_returns_none(self):
        assert await LinkPreviewClient().fetch("ftp://example.com/") is None


@pytest.fixture
def svc():
    service = WebLinkService(AsyncMock(), AsyncMock(), None)
    service._repo, service._trip_repo, service._place_repo = AsyncMock(), AsyncMock(), AsyncMock()
    service._trip_repo.get_trip.return_value = SimpleNamespace(id=1, name="Example trip")
    service._place_repo.get_place.return_value = SimpleNamespace(id=3, name="Cafe Example")
    service._preview.fetch.return_value = LinkPreview("Fetched title", "Fetched desc", "https://example.com/i.jpg")
    service._repo.create_link.side_effect = lambda data: _link(**{**data, "id": 5, "trip_id": data.get("trip_id"), "place_id": data.get("place_id")})
    return service


class TestCreate:
    async def test_saves_the_fetched_preview(self, svc):
        link = await svc.create_trip_link(1, WebLinkCreate(url="https://example.com/a"))
        data = svc._repo.create_link.await_args.args[0]
        assert data["trip_id"] == 1 and "place_id" not in data
        assert (data["kind"], data["title"], data["description"]) == ("website", "Fetched title", "Fetched desc")
        assert link.id == 5

    async def test_the_users_title_and_kind_win(self, svc):
        await svc.create_place_link(3, WebLinkCreate(url="https://example.com/a", title="Mine", kind="booking"))
        data = svc._repo.create_link.await_args.args[0]
        assert (data["place_id"], data["title"], data["kind"]) == (3, "Mine", "booking")

    @pytest.mark.parametrize("url,kind", [("https://www.instagram.com/p/x/", "instagram"), ("https://www.tiktok.com/@a/video/1", "tiktok")])
    async def test_social_links_skip_the_fetch(self, svc, url, kind):
        await svc.create_trip_link(1, WebLinkCreate(url=url))
        svc._preview.fetch.assert_not_awaited()
        data = svc._repo.create_link.await_args.args[0]
        assert (data["kind"], data["title"], data["image_url"]) == (kind, None, None)

    async def test_a_failed_fetch_still_saves(self, svc):
        svc._preview.fetch.return_value = None
        await svc.create_trip_link(1, WebLinkCreate(url="https://example.com/a"))
        data = svc._repo.create_link.await_args.args[0]
        assert (data["title"], data["description"], data["image_url"]) == (None, None, None)

    async def test_unknown_parents(self, svc):
        svc._trip_repo.get_trip.return_value = None
        svc._place_repo.get_place.return_value = None
        with pytest.raises(TravelNotFoundError):
            await svc.create_trip_link(9, WebLinkCreate(url="https://example.com/a"))
        with pytest.raises(TravelNotFoundError):
            await svc.create_place_link(9, WebLinkCreate(url="https://example.com/a"))
        svc._preview.fetch.assert_not_awaited()

    async def test_duplicate_is_a_conflict(self, svc):
        svc._repo.create_link.side_effect = IntegrityError("x", {}, Exception("dup"))
        with pytest.raises(TravelConflictError):
            await svc.create_trip_link(1, WebLinkCreate(url="https://example.com/a"))
        svc._session.rollback.assert_awaited_once()


class TestUpdate:
    async def test_unknown_link(self, svc):
        svc._repo.get_link.return_value = None
        assert await svc.update_link(9, WebLinkUpdate(title="x")) is None

    async def test_a_title_edit_does_not_refetch(self, svc):
        svc._repo.get_link.return_value = _link()
        svc._repo.update_link.return_value = _link(title="New")
        await svc.update_link(1, WebLinkUpdate(title="New"))
        svc._preview.fetch.assert_not_awaited()
        assert svc._repo.update_link.await_args.args == (1, {"title": "New"})

    async def test_a_new_url_refetches_and_reguesses_the_kind(self, svc):
        svc._repo.get_link.return_value = _link()
        svc._repo.update_link.return_value = _link()
        await svc.update_link(1, WebLinkUpdate(url="https://youtu.be/abc"))
        changes = svc._repo.update_link.await_args.args[1]
        assert changes["kind"] == "video" and changes["title"] == "Fetched title" and changes["image_url"] == "https://example.com/i.jpg"

    async def test_a_new_url_keeps_a_title_given_with_it(self, svc):
        svc._repo.get_link.return_value = _link()
        svc._repo.update_link.return_value = _link()
        await svc.update_link(1, WebLinkUpdate(url="https://example.com/b", title="Mine"))
        assert svc._repo.update_link.await_args.args[1]["title"] == "Mine"

    async def test_nulling_the_url_is_refused(self, svc):
        svc._repo.get_link.return_value = _link()
        with pytest.raises(ValueError):
            await svc.update_link(1, WebLinkUpdate.model_validate({"kind": None}))

    async def test_duplicate_is_a_conflict(self, svc):
        svc._repo.get_link.return_value = _link()
        svc._repo.update_link.side_effect = IntegrityError("x", {}, Exception("dup"))
        with pytest.raises(TravelConflictError):
            await svc.update_link(1, WebLinkUpdate(title="x"))


class TestDeleteAndList:
    async def test_delete(self, svc):
        svc._repo.delete_link.return_value = True
        assert await svc.delete_link(1) is True
        svc._repo.delete_link.return_value = False
        assert await svc.delete_link(1) is False

    async def test_lists_need_an_existing_parent(self, svc):
        svc._repo.get_links.return_value = [_link()]
        assert len(await svc.get_trip_links(1)) == 1
        svc._place_repo.get_place.return_value = None
        with pytest.raises(TravelNotFoundError):
            await svc.get_place_links(3)


class TestNoteIndex:
    async def test_notes_are_indexed_with_the_parent_name(self):
        embeddings = MagicMock()
        embeddings.delete_by_source = AsyncMock()
        service = WebLinkService(AsyncMock(), AsyncMock(), embeddings)
        service._repo, service._trip_repo, service._place_repo = AsyncMock(), AsyncMock(), AsyncMock()
        service._trip_repo.get_trip.return_value = SimpleNamespace(id=1, name="Example trip")
        service._preview.fetch.return_value = LinkPreview()
        service._repo.create_link.return_value = _link(notes="Great tips", title="Visit Example")
        await service.create_trip_link(1, WebLinkCreate(url="https://example.com/a", notes="Great tips"))
        embedded = embeddings.embed_background.call_args.args[0]
        assert (embedded.source_type, embedded.source_id) == ("web_link_note", 1)
        assert embedded.content == "Link for Example trip (Visit Example): Great tips"
