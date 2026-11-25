from typing import Any

from pydantic import BaseModel


class SettingFieldRead(BaseModel):
    """One setting as the /settings page shows it. The value is not here: it comes from `read_path`."""

    key: str
    field: str
    label: str
    description: str | None = None
    widget: str
    # JSON Schema type of the value: integer, number, string, boolean, array or object.
    type: str
    # Allowed values: the entries of an enum, or the keys of an object (the cascade profiles).
    options: list[str] | None = None
    min: float | None = None
    max: float | None = None
    max_length: int | None = None
    step: float | None = None
    # Can be cleared (sent as null) to leave it unset.
    nullable: bool
    has_default: bool
    default: Any = None
    unit: str | None = None
    group: str | None = None
    confirm_note: str | None = None
    href: str | None = None
    read_path: str
    # With an `{entry}` placeholder, the value is an object written one entry at a time as {entry_field: value}.
    write_path: str
    entry_field: str | None = None
    # Other fields this control sets with its own (they have widget "hidden").
    covers: list[str] | None = None
    # A tuning knob: the page shows it only with "Show tuning" on (or when a search matches it).
    advanced: bool = False


class SettingsLinkRead(BaseModel):
    """Something edited on another page, shown as a link row in its section."""

    label: str
    href: str
    description: str | None = None


class SettingsNamespaceRead(BaseModel):
    namespace: str
    title: str
    description: str
    fields: list[SettingFieldRead]
    links: list[SettingsLinkRead] = []


class StoredSettingRead(BaseModel):
    key: str
    value: str


class SettingsCatalogRead(BaseModel):
    namespaces: list[SettingsNamespaceRead]
    # Stored keys no field covers (checklist template, pause state, ...), shown read-only. Never `assistant.*`.
    unregistered: list[StoredSettingRead]
