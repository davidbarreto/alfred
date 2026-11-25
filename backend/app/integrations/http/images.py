"""Download an image from a public URL, with the same public-host guard as link previews.

Knows nothing about cities: only HTTP and image bytes."""
import logging
from urllib.parse import urljoin, urlsplit

import httpx

from app.integrations.link_preview.client import UnsafeUrlError, assert_public_url
from app.shared.protocols.media import FetchedImage

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
MAX_IMAGE_BYTES = 5_000_000
_MAX_REDIRECTS = 3


def sniff_image_type(data: bytes) -> str | None:
    """The image type the bytes start with; None for anything that isn't a JPEG, PNG, WebP or GIF."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


class HttpImageFetcher:
    def __init__(self, user_agent: str):
        self._user_agent = user_agent

    async def fetch(self, url: str) -> FetchedImage | None:
        try:
            return await self._fetch(url)
        except UnsafeUrlError as exc:
            logger.warning("Image fetch refused: host=%s reason=%s", urlsplit(url).hostname, exc)
        except httpx.HTTPError as exc:
            logger.warning("Image fetch failed: host=%s error=%s", urlsplit(url).hostname, exc)
        return None

    async def _fetch(self, url: str) -> FetchedImage | None:
        headers = {"User-Agent": self._user_agent, "Accept": "image/*"}
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=False, headers=headers) as client:
            current = url
            for _ in range(_MAX_REDIRECTS + 1):
                await assert_public_url(current)
                async with client.stream("GET", current) as response:
                    if response.is_redirect and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    response.raise_for_status()
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_IMAGE_BYTES:
                            logger.warning("Image fetch failed: host=%s error=larger than %d bytes", urlsplit(url).hostname, MAX_IMAGE_BYTES)
                            return None
                    content_type = sniff_image_type(body)
                    if content_type is None:
                        logger.warning("Image fetch failed: host=%s error=not an image", urlsplit(url).hostname)
                        return None
                    return FetchedImage(data=body, content_type=content_type)
        logger.warning("Image fetch failed: host=%s error=too many redirects", urlsplit(url).hostname)
        return None
