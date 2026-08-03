from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://codeforces.com/api"
_PAGE_SIZE = 100
_REQUEST_DELAY_SECONDS = 2.0


class CodeforcesClient:
    """Thin wrapper around the public Codeforces API. No auth required."""

    async def _get(self, method: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(f"{_BASE_URL}/{method}", params=params)
        body = resp.json()
        if body.get("status") != "OK":
            logger.error("Codeforces API error: method=%s comment=%s", method, body.get("comment"))
            resp.raise_for_status()
        return body["result"]

    async def get_user_info(self, handle: str) -> dict:
        result = await self._get("user.info", {"handles": handle})
        return result[0]

    async def get_problemset_statistics(self) -> dict[str, int]:
        """Bulk solvedCount per problem, keyed by f"{contestId}{index}" (matches Problem.external_id)."""
        result = await self._get("problemset.problems", {})
        return {
            f"{problem['contestId']}{problem['index']}": stats.get("solvedCount")
            for problem, stats in zip(result["problems"], result["problemStatistics"])
        }

    async def get_submissions_since(self, handle: str, last_external_id: str | None) -> list[dict]:
        """Paginate user.status (newest first) until the stored watermark is reached."""
        watermark = int(last_external_id) if last_external_id else None
        collected: list[dict] = []
        page_from = 1

        while True:
            page = await self._get(
                "user.status", {"handle": handle, "from": page_from, "count": _PAGE_SIZE}
            )
            if not page:
                break

            new_in_page = [s for s in page if watermark is None or s["id"] > watermark]
            collected.extend(new_in_page)

            if len(new_in_page) < len(page) or len(page) < _PAGE_SIZE:
                break

            page_from += _PAGE_SIZE
            await asyncio.sleep(_REQUEST_DELAY_SECONDS)

        return collected
