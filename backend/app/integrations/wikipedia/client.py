"""Cover photos from Wikimedia: a city's lead image on its English Wikipedia article, and the photos the picker offers
(the article's images, or a Commons search), all of them Wikimedia Commons files.

Only article titles (a city and country name) and the picker's search words are sent. The summary endpoint names the
lead image; the action API gives a 1600px rendition and the author and licence the Commons licences ask to show.
Every call is logged in `integration.provider_calls` with a summary (titles, file, size, credit), never image bytes."""
import html
import logging
import re
from urllib.parse import quote, unquote, urlsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.provider_calls.repository import create_sync_log
from app.shared.protocols.media import (
    CoverCandidate, CoverPhoto, CoverSource, CoverSourceBusyError, CoverSourceUnavailableError, ImageFetcher,
)

logger = logging.getLogger(__name__)

_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_API_URL = "https://en.wikipedia.org/w/api.php"
_COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
_TIMEOUT_SECONDS = 10.0
_WIDTH = 1600
# The picker: 400 px thumbnails of photos at least 1200 px wide, in the formats a cover can be.
_THUMB_WIDTH = 400
_MIN_WIDTH = 1200
_PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_NOT_PHOTOS = re.compile(r"(?<![a-z])(flag|map|locator|coat|logo|seal)", re.IGNORECASE)
_ARTICLE_IMAGES = 50
_SEARCH_RESULTS = 30
_PROVIDER = "wikipedia"
# Wikimedia asks automated clients to name themselves; no personal data goes here.
USER_AGENT = "AlfredCityCovers/1.0 (self-hosted personal assistant; city cover photos)"
_TAGS = re.compile(r"<[^>]+>")


def _plain(value: str | None) -> str | None:
    """Commons metadata is HTML ("<a href=...>Name</a>"): keep the text."""
    if not value:
        return None
    text = " ".join(html.unescape(_TAGS.sub("", value)).split())
    return text or None


def file_name(image_url: str) -> str | None:
    """`File:` title of an upload.wikimedia.org URL: the original's last path segment.

    Some summaries give a thumbnail instead (`.../thumb/a/ab/<File>/3840px-<File>`): its file is the segment before.
    """
    parts = urlsplit(image_url)
    if not parts.hostname or not parts.hostname.endswith("wikimedia.org"):
        return None
    segments = [s for s in parts.path.split("/") if s]
    if "thumb" in segments and len(segments) >= 2:
        segment = segments[-2]
    else:
        segment = segments[-1] if segments else ""
    return unquote(segment) or None


def credit_text(metadata: dict) -> str:
    artist = _plain((metadata.get("Artist") or {}).get("value"))
    licence = _plain((metadata.get("LicenseShortName") or {}).get("value"))
    parts = [p for p in (artist, licence) if p]
    return f"Photo: {', '.join(parts)}, via Wikimedia Commons" if parts else "Photo via Wikimedia Commons"


def _candidate(page: dict) -> CoverCandidate | None:
    """A picker photo from an action API page, or None when it is not one (format, size, or a flag, map or emblem)."""
    title = page.get("title") or ""
    infos = page.get("imageinfo") or []
    if not infos or _NOT_PHOTOS.search(title):
        return None
    info = infos[0]
    width, height = info.get("width") or 0, info.get("height") or 0
    if info.get("mime") not in _PHOTO_TYPES or width < _MIN_WIDTH or not info.get("thumburl"):
        return None
    return CoverCandidate(
        title=title, thumb_url=info["thumburl"], width=width, height=height,
        credit=credit_text(info.get("extmetadata") or {}), page_url=info.get("descriptionurl") or "",
    )


def strip_file_prefix(value: str) -> str:
    """A Commons file title without its "File:" prefix (the picker sends it with)."""
    value = value.strip()
    return value[5:].strip() if value.lower().startswith("file:") else value


class WikipediaClient:
    def __init__(self, images: ImageFetcher):
        self._images = images

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})

    async def find(self, titles: list[str], session: AsyncSession | None = None) -> CoverPhoto | None:
        found, summary, error = None, None, None
        try:
            async with self._http() as client:
                for title in titles:
                    result = await self._find(client, title)
                    if result is not None:
                        found, summary = result
                        summary = {"title": title, **summary}
                        break
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Wikipedia cover lookup failed: error=%s", exc)
            error = str(exc) or type(exc).__name__
        await self._log(session, "find_cover", titles[0] if titles else None, {"titles": titles},
                        summary or ({"found": False} if error is None else None), error)
        return found

    async def candidates(
        self, source: CoverSource, titles: list[str], query: str, session: AsyncSession | None = None,
    ) -> list[CoverCandidate]:
        request = {"source": source, "titles": titles} if source == "article" else {"source": source, "query": query}
        entity = (titles[0] if titles else None) if source == "article" else query
        try:
            async with self._http() as client:
                if source == "article":
                    pages: list[dict] = []
                    for title in titles:
                        pages = await self._pages(client, _API_URL, {
                            "generator": "images", "gimlimit": str(_ARTICLE_IMAGES), "titles": title, "redirects": "1",
                        })
                        if pages:
                            break
                else:
                    pages = await self._pages(client, _COMMONS_API_URL, {
                        "generator": "search", "gsrsearch": query, "gsrnamespace": "6", "gsrlimit": str(_SEARCH_RESULTS),
                    })
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            busy = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
            logger.warning("Wikimedia cover candidates failed: source=%s busy=%s error=%s", source, busy, exc)
            await self._log(session, "cover_candidates", entity, request, None, str(exc) or type(exc).__name__)
            if busy:
                raise CoverSourceBusyError("Wikimedia is busy, try again in a minute") from exc
            raise CoverSourceUnavailableError("Wikimedia could not be reached") from exc
        # A search ranks its pages ("index"); an article's images come in its own order.
        pages = sorted(pages, key=lambda p: p.get("index", 0))
        found = [c for c in (_candidate(p) for p in pages) if c is not None]
        await self._log(session, "cover_candidates", entity, request,
                        {"pages": len(pages), "photos": len(found), "files": [c.title for c in found[:10]]}, None)
        return found

    async def from_file(self, file_title: str, session: AsyncSession | None = None) -> CoverPhoto | None:
        name = strip_file_prefix(file_title)
        found, summary, error = None, None, None
        try:
            async with self._http() as client:
                result = await self._photo(client, name, None) if name else None
                if result is not None:
                    found, summary = result
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Wikimedia Commons file fetch failed: error=%s", exc)
            error = str(exc) or type(exc).__name__
        await self._log(session, "fetch_cover", name or None, {"file": name},
                        summary or ({"found": False} if error is None else None), error)
        return found

    async def _find(self, client: httpx.AsyncClient, title: str) -> tuple[CoverPhoto, dict] | None:
        response = await client.get(_SUMMARY_URL + quote(title.replace(" ", "_"), safe=""), params={"redirect": "true"})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        summary = response.json()
        original = (summary.get("originalimage") or {}).get("source")
        if summary.get("type") == "disambiguation" or not original:
            return None
        name = file_name(original)
        if name is None:
            return None
        page = ((summary.get("content_urls") or {}).get("desktop") or {}).get("page") or original
        return await self._photo(client, name, page)

    async def _photo(self, client: httpx.AsyncClient, name: str, fallback_page: str | None) -> tuple[CoverPhoto, dict] | None:
        """The file at 1600 px with its credit, and a summary of it for the provider-call log."""
        info = await self._image_info(client, name)
        if info is None:
            return None
        image = await self._images.fetch(info.get("thumburl") or info["url"])
        if image is None:
            return None
        credit = credit_text(info.get("extmetadata") or {})
        page = info.get("descriptionurl") or fallback_page or info["url"]
        logger.debug("Wikimedia cover fetched: file=%r", name)
        summary = {"file": name, "width": info.get("width"), "height": info.get("height"), "bytes": len(image.data),
                   "credit": credit}
        return CoverPhoto(image=image, credit=credit, source_url=page), summary

    async def _image_info(self, client: httpx.AsyncClient, name: str) -> dict | None:
        params = {
            "action": "query", "format": "json", "formatversion": "2", "prop": "imageinfo",
            "iiprop": "url|size|extmetadata", "iiurlwidth": str(_WIDTH), "titles": f"File:{name}",
        }
        response = await client.get(_API_URL, params=params)
        response.raise_for_status()
        pages = (response.json().get("query") or {}).get("pages") or []
        infos = pages[0].get("imageinfo") if pages else None
        return infos[0] if infos else None

    async def _pages(self, client: httpx.AsyncClient, url: str, generator: dict[str, str]) -> list[dict]:
        """Generated File pages with their imageinfo (thumbnail, size, type, author and licence)."""
        params = {
            "action": "query", "format": "json", "formatversion": "2", "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(_THUMB_WIDTH),
            "iiextmetadatafilter": "Artist|LicenseShortName", **generator,
        }
        response = await client.get(url, params=params)
        response.raise_for_status()
        return (response.json().get("query") or {}).get("pages") or []

    async def _log(
        self, session: AsyncSession | None, operation: str, entity_id: str | None, request: dict,
        response: dict | None, error: str | None,
    ) -> None:
        if session is None:
            return
        try:
            await create_sync_log(
                session, provider=_PROVIDER, operation=operation, entity_type="cover_photo",
                provider_entity_id=entity_id[:255] if entity_id else None, status="error" if error else "ok",
                request_payload=request, response_payload=response, error=error,
            )
        except Exception:
            logger.warning("Failed to write integration sync log", exc_info=True)
