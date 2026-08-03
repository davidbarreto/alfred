from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://leetcode.com/graphql"
_PAGE_SIZE = 20
_REQUEST_DELAY_SECONDS = 1.0

_SUBMISSION_LIST_QUERY = """
query submissionList($offset: Int!, $limit: Int!) {
  submissionList(offset: $offset, limit: $limit) {
    hasNext
    submissions {
      id
      titleSlug
      lang
      statusDisplay
      timestamp
    }
  }
}
"""

_QUESTION_DATA_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    difficulty
    topicTags { name }
  }
}
"""


class LeetCodeAuthError(Exception):
    """The stored LEETCODE_SESSION/csrftoken cookies were rejected or have expired."""


class LeetCodeClient:
    """Wraps LeetCode's unofficial GraphQL API using an authenticated session cookie.

    The session cookie is a static value copied from a logged-in browser session
    (see app/config.py), not a refreshable OAuth token -- it needs manual renewal
    when it expires, which surfaces as a LeetCodeAuthError.
    """

    def __init__(self, session_cookie: str, csrf_token: str) -> None:
        self._session_cookie = session_cookie
        self._csrf_token = csrf_token

    async def _post(self, query: str, variables: dict) -> dict:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                _GRAPHQL_URL,
                json={"query": query, "variables": variables},
                cookies={"LEETCODE_SESSION": self._session_cookie, "csrftoken": self._csrf_token},
                headers={
                    "x-csrftoken": self._csrf_token,
                    "referer": "https://leetcode.com/problemset/all/",
                    "content-type": "application/json",
                },
            )
        if resp.status_code in (401, 403):
            logger.error("LeetCode auth rejected: status=%d", resp.status_code)
            raise LeetCodeAuthError("LeetCode session cookie rejected or expired")
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body:
            logger.error("LeetCode GraphQL error: %s", body["errors"])
            raise RuntimeError(f"LeetCode GraphQL error: {body['errors']}")
        return body["data"]

    async def get_submissions_since(self, last_external_id: str | None) -> list[dict]:
        """Paginate submissionList (newest first) until the stored watermark is reached."""
        watermark = int(last_external_id) if last_external_id else None
        collected: list[dict] = []
        offset = 0

        while True:
            data = await self._post(_SUBMISSION_LIST_QUERY, {"offset": offset, "limit": _PAGE_SIZE})
            page = data["submissionList"]["submissions"]
            has_next = data["submissionList"]["hasNext"]
            if not page:
                break

            new_in_page = [s for s in page if watermark is None or int(s["id"]) > watermark]
            collected.extend(new_in_page)

            if len(new_in_page) < len(page) or not has_next:
                break

            offset += _PAGE_SIZE
            await asyncio.sleep(_REQUEST_DELAY_SECONDS)

        return collected

    async def get_question_data(self, title_slug: str) -> dict:
        data = await self._post(_QUESTION_DATA_QUERY, {"titleSlug": title_slug})
        return data["question"]
