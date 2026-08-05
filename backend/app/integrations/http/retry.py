from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.5


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    retryable_status_codes: frozenset[int] = DEFAULT_RETRYABLE_STATUS_CODES,
) -> httpx.Response:
    """Issue an HTTP request, retrying on transient (e.g. 5xx/429) failures.

    Raises `httpx.HTTPStatusError` if the final attempt still fails, or immediately
    for non-retryable status codes.
    """
    for attempt in range(1, max_attempts + 1):
        response = await client.request(method, url, params=params)
        if response.status_code not in retryable_status_codes:
            response.raise_for_status()
            return response
        if attempt == max_attempts:
            response.raise_for_status()
        logger.warning(
            "HTTP request failed, retrying: url=%s status=%d attempt=%d/%d",
            url,
            response.status_code,
            attempt,
            max_attempts,
        )
        await asyncio.sleep(backoff_seconds * attempt)
    raise AssertionError("unreachable")
