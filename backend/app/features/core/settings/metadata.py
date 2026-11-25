"""Field metadata for runtime settings, read by the settings catalog (`catalog.py`) to build the portal's /settings page.

Each settings `Update` schema declares its fields with `setting(...)`: the label and hint, plus the hints JSON Schema
cannot carry (which control to show, the unit, the fieldset). Limits stay ordinary Field constraints (`ge`, `le`,
`max_length`), so the API and the page check the same ones.
"""
from typing import Any, Literal

from pydantic import Field

Widget = Literal[
    "number", "toggle", "time", "text", "longtext", "weekdays", "windows", "city", "json", "readonly", "link",
]


def setting(
    title: str,
    description: str = "",
    *,
    widget: Widget | None = None,
    unit: str | None = None,
    group: str | None = None,
    confirm_note: str | None = None,
    href: str | None = None,
    step: float | None = None,
    key: str | None = None,
    write_path: str | None = None,
    entry_field: str | None = None,
    default: Any = None,
    **constraints: Any,
) -> Any:
    """A settings field: `title` is the label, `description` the hint under it.

    `widget` is needed only when the type alone does not say which control to use (a `str` can be a time, a short
    text or a long text). `confirm_note` is shown in the save dialog when the field changes (a side effect worth a
    second look). `href` links a read-only or link row to where the value is edited.

    `key` is the stored key when it is not `<namespace>.<field>`. `write_path` overrides the namespace's PUT; with an
    `{entry}` placeholder the value is a JSON object written one entry at a time, as `{entry_field: value}`.
    """
    extra = {
        name: value
        for name, value in {
            "widget": widget, "unit": unit, "group": group, "confirm_note": confirm_note, "href": href, "step": step,
            "key": key, "write_path": write_path, "entry_field": entry_field,
        }.items()
        if value is not None
    }
    return Field(default=default, title=title, description=description or None, json_schema_extra=extra, **constraints)
