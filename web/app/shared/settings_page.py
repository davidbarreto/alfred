"""The /settings page: sections built from the backend's settings catalog and each namespace's own GET.

Pure functions, so the page logic is unit-tested without the backend. The catalog says what each setting is (label,
control, limits, default, where it is read and written); the values come from the namespace GETs, fetched in parallel
by the route, so one failing namespace leaves only its own rows out.
"""
from typing import Any

UNREGISTERED_PREVIEW = 5

# Rows that show no value: the value is edited, and may be personal, on another page.
_VALUELESS_WIDGETS = {"link"}


def read_paths(catalog: dict) -> list[str]:
    """Each namespace GET the page needs, once, in catalog order."""
    paths: list[str] = []
    for namespace in catalog["namespaces"]:
        for field in namespace["fields"]:
            if field["read_path"] not in paths:
                paths.append(field["read_path"])
    return paths


def _summary(value: Any) -> list[str]:
    """A JSON object of lists as one line per entry: "normal: 1h, 10m, 0"."""
    if not isinstance(value, dict):
        return []
    return [f"{entry}: {', '.join(map(str, items)) if isinstance(items, list) else items}" for entry, items in value.items()]


def _row(field: dict, values: dict) -> dict:
    value = None if field["widget"] in _VALUELESS_WIDGETS else values.get(field["field"])
    row = {
        **field,
        "value": value,
        "modified": field["has_default"] and value != field["default"],
        "summary": _summary(value) if field["widget"] == "json" else [],
        "search": " ".join(filter(None, [field["label"], field["key"], field.get("description")])).lower(),
    }
    if field["widget"] == "city":
        # The picker shows the city's name: the GET returns the object next to its id (home_city_id -> home_city).
        row["city"] = values.get(field["field"].removesuffix("_id"))
    return row


def _groups(rows: list[dict]) -> list[dict]:
    """Rows grouped by fieldset, in order of first appearance; rows without a group come first."""
    groups: list[dict] = []
    for row in rows:
        name = row.get("group")
        group = next((g for g in groups if g["name"] == name), None)
        if group is None:
            group = {"name": name, "rows": []}
            groups.insert(0, group) if name is None else groups.append(group)
        group["rows"].append(row)
    return groups


def build_sections(catalog: dict, values_by_path: dict[str, dict | None]) -> list[dict]:
    """One section per namespace. Rows whose GET failed are left out and the section says so."""
    sections = []
    for namespace in catalog["namespaces"]:
        rows, failed = [], False
        for field in namespace["fields"]:
            values = values_by_path.get(field["read_path"])
            if values is None:
                failed = True
                continue
            rows.append(_row(field, values))
        sections.append({
            "namespace": namespace["namespace"],
            "title": namespace["title"],
            "description": namespace["description"],
            "links": namespace.get("links", []),
            "groups": _groups(rows),
            "count": len(rows),
            "load_error": failed,
        })
    return sections


def unregistered_preview(catalog: dict) -> tuple[list[dict], int]:
    rows = catalog.get("unregistered", [])
    return rows[:UNREGISTERED_PREVIEW], len(rows)
