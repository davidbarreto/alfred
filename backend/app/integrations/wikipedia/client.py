"""A city's cover photo: the lead image of its English Wikipedia article, which is a Wikimedia Commons file.

Only article titles (a city and country name) are sent. The summary endpoint names the lead image; the action API
gives a 1600px rendition and the author and licence the Commons licences ask to show."""
import html
import logging
import re
from urllib.parse import quote, unquote, urlsplit

import httpx

from app.shared.protocols.media import CoverPhoto, ImageFetcher

logger = logging.getLogger(__name__)

_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_API_URL = "https://en.wikipedia.org/w/api.php"
_TIMEOUT_SECONDS = 10.0
_WIDTH = 1600
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


class WikipediaClient:
    def __init__(self, images: ImageFetcher):
        self._images = images

    async def find(self, titles: list[str]) -> CoverPhoto | None:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
                for title in titles:
                    found = await self._find(client, title)
                    if found is not None:
                        return found
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Wikipedia cover lookup failed: error=%s", exc)
        return None

    async def _find(self, client: httpx.AsyncClient, title: str) -> CoverPhoto | None:
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
        info = await self._image_info(client, name)
        if info is None:
            return None
        image = await self._images.fetch(info.get("thumburl") or info["url"])
        if image is None:
            return None
        page = info.get("descriptionurl") or ((summary.get("content_urls") or {}).get("desktop") or {}).get("page") or original
        logger.debug("Wikipedia cover found: title=%r file=%r", title, name)
        return CoverPhoto(image=image, credit=credit_text(info.get("extmetadata") or {}), source_url=page)

    async def _image_info(self, client: httpx.AsyncClient, name: str) -> dict | None:
        params = {
            "action": "query", "format": "json", "formatversion": "2", "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": str(_WIDTH), "titles": f"File:{name}",
        }
        response = await client.get(_API_URL, params=params)
        response.raise_for_status()
        pages = (response.json().get("query") or {}).get("pages") or []
        infos = pages[0].get("imageinfo") if pages else None
        return infos[0] if infos else None
