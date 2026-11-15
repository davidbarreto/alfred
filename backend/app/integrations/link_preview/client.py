"""Fetch the title, description and image a web page declares about itself (Open Graph tags).

The URL comes from the user, but the backend sits next to the database and other internal services, so every
request (and every redirect hop) is refused unless the host resolves only to public addresses.
Knows nothing about travel: only HTTP and HTML."""
import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0
_MAX_BYTES = 1_000_000
_MAX_REDIRECTS = 3
_USER_AGENT = "Mozilla/5.0 (compatible; AlfredLinkPreview/1.0)"


@dataclass(frozen=True)
class LinkPreview:
    title: str | None = None
    description: str | None = None
    image_url: str | None = None


class UnsafeUrlError(Exception):
    """The URL points somewhere the backend must not fetch (non-http scheme, private or unresolvable host)."""


async def assert_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeUrlError("only http and https addresses are fetched")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"host does not resolve: {parts.hostname}") from exc
    if not infos:
        raise UnsafeUrlError(f"host does not resolve: {parts.hostname}")
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise UnsafeUrlError("host resolves to a non-public address")


class _MetaParser(HTMLParser):
    """Collects og:/twitter: meta tags and the <title> text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            values = dict(attrs)
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content")
            if key and content and key not in self.meta:
                self.meta[key] = content.strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def parse_preview(html: str, base_url: str) -> LinkPreview:
    parser = _MetaParser()
    parser.feed(html)
    meta = parser.meta
    title = meta.get("og:title") or meta.get("twitter:title") or " ".join(parser.title.split()) or None
    description = meta.get("og:description") or meta.get("twitter:description") or meta.get("description") or None
    image = meta.get("og:image") or meta.get("twitter:image") or None
    if image:
        image = urljoin(base_url, image)
        if urlsplit(image).scheme not in ("http", "https"):
            image = None
    return LinkPreview(title=title, description=description, image_url=image)


class LinkPreviewClient:
    async def fetch(self, url: str) -> LinkPreview | None:
        """The page's preview, or None when it can't be fetched or read (never raises)."""
        try:
            return await self._fetch(url)
        except UnsafeUrlError as exc:
            logger.warning("Link preview refused: host=%s reason=%s", urlsplit(url).hostname, exc)
        except (httpx.HTTPError, UnicodeError) as exc:
            logger.warning("Link preview failed: host=%s error=%s", urlsplit(url).hostname, exc)
        return None

    async def _fetch(self, url: str) -> LinkPreview | None:
        headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=False, headers=headers) as client:
            current = url
            for _ in range(_MAX_REDIRECTS + 1):
                await assert_public_url(current)
                async with client.stream("GET", current) as response:
                    if response.is_redirect and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type", "").lower():
                        return None
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) >= _MAX_BYTES:
                            break
                    html = body[:_MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
                    return parse_preview(html, current)
        logger.warning("Link preview failed: host=%s error=too many redirects", urlsplit(url).hostname)
        return None
