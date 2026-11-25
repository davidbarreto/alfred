"""The read-only link groups shown on trip and place pages (each city's and country's travel links)."""
from app.shared.forward import safe_get

LINK_KINDS = ["website", "instagram", "tiktok", "video", "article", "map", "booking", "other"]
# Rows a links card shows before its "See all" link.
LINKS_PREVIEW = 5


async def link_groups(cities: list[dict], own_urls: set[str], with_countries: bool = True) -> list[dict]:
    """Read-only link groups for a trip or place page: each city, then each country in order of first appearance.

    A URL already shown higher on the page (the page's own links, an earlier group) is not repeated; empty groups are
    left out; each group shows at most `LINKS_PREVIEW` and links to the owner's full links page.
    """
    seen = set(own_urls)
    groups: list[dict] = []

    async def add(title: str, kind: str, owner_id: int) -> None:
        links = await safe_get(f"/travel/{kind}/{owner_id}/links", default=[]) or []
        fresh = [link for link in links if link["url"] not in seen]
        seen.update(link["url"] for link in fresh)
        if fresh:
            groups.append({"title": title, "see_all": f"/travel/{kind}/{owner_id}/links", "total": len(links), "links": fresh[:LINKS_PREVIEW]})

    countries: dict[int, dict] = {}
    for city in cities:
        await add(city["name"], "cities", city["id"])
        countries.setdefault(city["country"]["id"], city["country"])
    for country in countries.values() if with_countries else []:
        await add(country["name"], "countries", country["id"])
    return groups
