import time
import requests
from typing import Any, Generator

def _get_nested(data: dict, path: str, default=None) -> Any:
    """
    Resolve a dot-notation path against a nested dict.

    Examples:
        _get_nested(data, "content")                 → data["content"]
        _get_nested(data, "meta.pagination.isLast")  → data["meta"]["pagination"]["isLast"]
    """
    if not path:
        return data
    for key in path.split("."):
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
    return data

def fetch_page(url: str, page: int, page_size: int = 32, **kwargs) -> dict:
    """
    Fetch a single page from the API.

    `kwargs` are passed as extra query params (e.g. storeId, category, etc.)
    """
    params = {"page": page, "size": page_size, **kwargs}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()

def paginate(
    url: str,
    page_size: int = 32,
    delay: float = 0.0,
    max_pages: int | None = None,
    content_key: str = "content",
    last_key: str = "last",
    total_pages_key: str = "totalPages",
    **kwargs,
) -> Generator[list[Any], None, None]:
    """
    Lazily iterate over all pages of the API, yielding each page's content list.

    Args:
        url:             API endpoint.
        page_size:       Items per page (should match what the API accepts).
        delay:           Seconds to wait between requests (polite crawling).
        max_pages:       Safety cap — stop after this many pages regardless of `last_key`.
        content_key:     Dot-notation path to the list of items  (default: "content").
        last_key:        Dot-notation path to the boolean is-last-page flag (default: "last").
        total_pages_key: Dot-notation path to the total page count (default: "totalPages").
        **kwargs:        Extra query params forwarded to every request.

    Yields:
        The content list from each page response.

    Examples:
        # IKEA API (flat structure, defaults work as-is)
        for items in paginate("https://api.ikea.com/offers", storeId=499):
            ...

        # API with nested pagination metadata
        for items in paginate(
            "https://api.example.com/products",
            content_key="data.results",
            last_key="meta.pagination.isLast",
            total_pages_key="meta.pagination.totalPages",
        ):
            ...
    """
    page = 0

    while True:
        data = fetch_page(url, page=page, page_size=page_size, **kwargs)

        content = _get_nested(data, content_key, default=[])
        yield content

        # ── Pagination guards ──────────────────────────────────────────────
        if _get_nested(data, last_key, default=True):
            break  # API says this is the final page

        total_pages = _get_nested(data, total_pages_key, default=1)
        if page + 1 >= total_pages:
            break  # cross-check against totalPages

        if max_pages is not None and page + 1 >= max_pages:
            break  # safety cap

        page += 1

        if delay:
            time.sleep(delay)

def fetch_all(
    url: str,
    page_size: int = 32,
    delay: float = 0.0,
    max_pages: int | None = None,
    content_key: str = "content",
    last_key: str = "last",
    total_pages_key: str = "totalPages",
    **kwargs,
) -> list[Any]:
    """
    Convenience wrapper: fetch every page and return a flat list of all items.

    Use `paginate()` instead if the dataset might be large and you want
    to process items incrementally without loading everything into memory.
    """
    all_items = []
    for page_content in paginate(
        url,
        page_size=page_size,
        delay=delay,
        max_pages=max_pages,
        content_key=content_key,
        last_key=last_key,
        total_pages_key=total_pages_key,
        **kwargs,
    ):
        all_items.extend(page_content)
    return all_items

# ── Quick smoke-test (replace URL + params with real values) ───────────────
if __name__ == "__main__":
    API_URL = "https://api.example.com/offers"

    total = 0
    for page_items in paginate(API_URL, page_size=32, delay=0.2, storeId=499):
        print(f"  Got {len(page_items)} items on this page")
        for item in page_items:
            print(f"    - [{item.get('storeId')}] {item.get('title')} "
                f"| min {item.get('minPrice')} {item.get('currency')}")
        total += len(page_items)

    print(f"\nTotal items fetched: {total}")