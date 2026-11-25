"""The /settings page: sections built from the backend's settings catalog and each namespace's own GET.

Pure functions, so the page logic is unit-tested without the backend. The catalog says what each setting is (label,
control, limits, default, where it is read and written); the values come from the namespace GETs, fetched in parallel
by the route, so one failing namespace leaves only its own rows out.
"""
from typing import Any

# Fields set through another row's control (its `covers`), never shown on their own.
_HIDDEN_WIDGETS = {"hidden"}
# Rows the page never sends.
READ_ONLY_WIDGETS = {"readonly"}


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


def _value(field: dict, values: dict) -> Any:
    """The row's value: one field's, or {field: value} over the field and the ones it covers (the weather place).

    A checklist keeps only what its PUT takes, so the loaded value compares equal to the one the page reads back.
    """
    if field["widget"] == "checklist":
        return [
            {"anchor": item["anchor"], "name": item["name"], "offset_days": item["offset_days"]}
            for item in values.get(field["field"]) or []
        ]
    if field.get("covers"):
        return {name: values.get(name) for name in [field["field"], *field["covers"]]}
    return values.get(field["field"])


def _row(field: dict, values: dict) -> dict:
    value = _value(field, values)
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
    if field["widget"] == "place":
        # The namespace GET lists what can be picked and what is in use now.
        row["choices"] = values.get("choices") or {"places": [], "cities": []}
        row["place_label"] = values.get("place_label")
    if field.get("reference"):
        # Shown read-only next to the editor (the base persona next to the additions).
        row["reference_text"] = values.get(field["reference"]) or ""
    return row


def _groups(rows: list[dict]) -> list[dict]:
    """Rows grouped by fieldset, in order of first appearance; rows without a group come first and tuning groups
    (every row `advanced`) last."""
    groups: list[dict] = []
    for row in rows:
        name = row.get("group")
        group = next((g for g in groups if g["name"] == name), None)
        if group is None:
            group = {"name": name, "rows": []}
            groups.insert(0, group) if name is None else groups.append(group)
        group["rows"].append(row)
    for group in groups:
        group["advanced"] = all(r.get("advanced") for r in group["rows"])
    return sorted(groups, key=lambda g: g["advanced"])


def build_sections(
    catalog: dict, values_by_path: dict[str, dict | None], notes: dict[str, str] | None = None
) -> list[dict]:
    """One section per namespace. Rows whose GET failed are left out and the section says so.

    `notes` adds a line of context under a section's description (finance: the current cycle).
    """
    sections = []
    for namespace in catalog["namespaces"]:
        rows, failed = [], False
        for field in namespace["fields"]:
            values = values_by_path.get(field["read_path"])
            if values is None:
                failed = True
                continue
            if field["widget"] not in _HIDDEN_WIDGETS:
                rows.append(_row(field, values))
        sections.append({
            "namespace": namespace["namespace"],
            "title": namespace["title"],
            "description": namespace["description"],
            "note": (notes or {}).get(namespace["namespace"]),
            "links": namespace.get("links", []),
            "groups": _groups(rows),
            "count": len(rows),
            # Only tuning knobs (chat, CS coach, metrics): hidden until "Show tuning" is on.
            "advanced": bool(rows) and all(r.get("advanced") for r in rows),
            "load_error": failed,
        })
    return sections


def section_notes(current_period: dict | None) -> dict[str, str]:
    """Context lines for sections, from data the route fetched next to the values."""
    notes = {}
    if current_period and current_period.get("year_month"):
        notes["finance"] = f"Current cycle: {current_period['year_month']}"
    return notes


class SaveError(ValueError):
    """A change the page should never send (unknown or read-only field)."""


def plan_writes(catalog: dict, changes: dict[str, dict[str, Any]]) -> dict[str, list[tuple[str, dict]]]:
    """The PUTs for a save, per namespace: `[(path, body), ...]`.

    Fields that share a write path go in one body. A field whose write path has an `{entry}` placeholder (the
    cascades) is a JSON object of changed entries, each written with its own PUT as `{entry_field: value}`.
    """
    by_key = {(ns["namespace"], f["field"]): f for ns in catalog["namespaces"] for f in ns["fields"]}
    plan: dict[str, list[tuple[str, dict]]] = {}
    for namespace, fields in changes.items():
        bodies: dict[str, dict] = {}
        writes: list[tuple[str, dict]] = []
        for name, value in fields.items():
            field = by_key.get((namespace, name))
            if field is None or field["widget"] in READ_ONLY_WIDGETS | _HIDDEN_WIDGETS:
                raise SaveError(f"{namespace}.{name} cannot be saved here")
            path = field["write_path"]
            if field.get("covers"):
                names = {name, *field["covers"]}
                if not isinstance(value, dict) or not set(value) <= names:
                    raise SaveError(f"{field['key']} must be an object with {', '.join(sorted(names))}")
                bodies.setdefault(path, {}).update(value)
            elif "{entry}" in path:
                if not isinstance(value, dict):
                    raise SaveError(f"{field['key']} must be a JSON object")
                options = field.get("options")
                for entry, entry_value in value.items():
                    if options and entry not in options:
                        raise SaveError(f"{field['key']}: unknown entry {entry!r}")
                    writes.append((path.replace("{entry}", entry), {field["entry_field"]: entry_value}))
            else:
                bodies.setdefault(path, {})[name] = value
        plan[namespace] = [*bodies.items(), *writes]
    return plan


def saved_values(catalog: dict, namespace: str, responses: list[dict]) -> dict[str, Any]:
    """The namespace's fields as the PUT responses returned them (each response is the full read model)."""
    fields = next((ns["fields"] for ns in catalog["namespaces"] if ns["namespace"] == namespace), [])
    merged: dict[str, Any] = {}
    for response in responses:
        merged.update(response or {})
    values: dict[str, Any] = {}
    for field in fields:
        if field["field"] not in merged or field["widget"] in _HIDDEN_WIDGETS:
            continue
        values[field["field"]] = _value(field, merged)
        if field["widget"] == "place":
            values["place_label"] = merged.get("place_label")
        if field["widget"] == "city":
            values[field["field"].removesuffix("_id")] = merged.get(field["field"].removesuffix("_id"))
    return values
