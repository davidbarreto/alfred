"""The settings catalog: every runtime setting with its label, control, limits and default, for the /settings page.

Built from the settings schemas' field metadata (`metadata.setting`) and each feature's `DEFAULTS`, so a new field
shows up on the page by being declared, and a field without a title fails the tests. Values are not here: the page
reads them from each namespace's own GET and writes through its own PUT, so feature validation and side effects
always run.
"""
import types
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from app.features.core.assistant_settings.schemas import AssistantSettingsRead, AssistantSettingsUpdate
from app.features.core.reminders.schemas import ReminderSettingsRead, ReminderSettingsUpdate
from app.features.core.reminders.settings_service import defaults as reminder_defaults
from app.features.core.settings.catalog_schemas import (
    SettingFieldRead,
    SettingsCatalogRead,
    SettingsLinkRead,
    SettingsNamespaceRead,
    StoredSettingRead,
)
from app.features.finance.settings.schemas import FinanceSettingsRead, FinanceSettingsUpdate
from app.features.finance.settings.service import DEFAULTS as FINANCE_DEFAULTS
from app.features.organizer.calendar_events.notification_settings.schemas import CalendarNotificationCascadesRead
from app.features.organizer.calendar_events.notification_settings.service import (
    DEFAULT_CASCADES as CALENDAR_CASCADES,
)
from app.features.organizer.contacts.notification_settings.schemas import ContactBirthdayCascadesRead
from app.features.organizer.contacts.notification_settings.service import DEFAULT_CASCADES as BIRTHDAY_CASCADES
from app.features.planning.schemas import PlanningSettingsRead, PlanningSettingsUpdate
from app.features.planning.settings_service import DEFAULTS as PLANNING_DEFAULTS
from app.features.study.settings.schemas import StudySettingsRead, StudySettingsUpdate
from app.features.study.settings.service import DEFAULTS as STUDY_DEFAULTS
from app.features.travel.settings_schemas import TravelSettingsRead, TravelSettingsUpdate
from app.features.travel.settings_service import DEFAULTS as TRAVEL_DEFAULTS

# Personal values: covered by fields, and never listed as raw rows even if a stray key is stored.
_PRIVATE_PREFIXES = ("assistant.",)

_WIDGET_BY_TYPE = {"integer": "number", "number": "number", "boolean": "toggle", "string": "text"}


@dataclass(frozen=True)
class CatalogSource:
    """One settings schema and the routes that read and write it.

    `schema` holds the fields and their metadata: the `Update` schema, or for the cascades the `Read` schema (their
    PUT takes one profile at a time). `read_schema` says which fields can be unset (None in the read model).
    """

    schema: type[BaseModel]
    read_schema: type[BaseModel]
    read_path: str
    write_path: str
    defaults: Callable[[], Mapping[str, Any]]
    exclude: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CatalogNamespace:
    namespace: str
    title: str
    description: str
    sources: tuple[CatalogSource, ...]
    links: tuple[SettingsLinkRead, ...] = field(default_factory=tuple)


NAMESPACES: tuple[CatalogNamespace, ...] = (
    CatalogNamespace(
        "planning", "Planning", "What Claude is told when it plans your days.",
        (CatalogSource(
            PlanningSettingsUpdate, PlanningSettingsRead, "/planning/settings", "/planning/settings",
            lambda: PLANNING_DEFAULTS,
            # Travel times are rows between locations; sending the list would replace every one of them.
            exclude=frozenset({"travel_times"}),
        ),),
        (SettingsLinkRead(label="Travel times", href="/locations", description="Edited on each location's page."),),
    ),
    CatalogNamespace(
        "reminders", "Reminders & overload",
        "When tasks escalate to urgent, when you count as overloaded, and the catch-up plan.",
        (CatalogSource(
            ReminderSettingsUpdate, ReminderSettingsRead, "/core/reminder-settings", "/core/reminder-settings",
            reminder_defaults,
        ),),
    ),
    CatalogNamespace(
        "travel", "Travel", "Getting to the airport, trip warnings and where trips start.",
        (CatalogSource(
            TravelSettingsUpdate, TravelSettingsRead, "/travel/settings", "/travel/settings", lambda: TRAVEL_DEFAULTS,
        ),),
        (SettingsLinkRead(label="Checklist template", href="/travel", description="Edited on the Travel page."),),
    ),
    CatalogNamespace(
        "finance", "Finance", "How the monthly finance cycle is counted.",
        (CatalogSource(
            FinanceSettingsUpdate, FinanceSettingsRead, "/finance/settings", "/finance/settings",
            lambda: FINANCE_DEFAULTS,
        ),),
        (SettingsLinkRead(label="Budget targets", href="/finance/budgets", description="Set per category."),),
    ),
    CatalogNamespace(
        "study", "Study", "Limits for study plans.",
        (CatalogSource(
            StudySettingsUpdate, StudySettingsRead, "/study/settings", "/study/settings", lambda: STUDY_DEFAULTS,
        ),),
    ),
    CatalogNamespace(
        "organizer", "Organizer", "Calendar and birthday notifications.",
        (
            CatalogSource(
                CalendarNotificationCascadesRead, CalendarNotificationCascadesRead,
                "/organizer/calendar-notification-settings", "/organizer/calendar-notification-settings",
                lambda: {"profiles": CALENDAR_CASCADES},
            ),
            CatalogSource(
                ContactBirthdayCascadesRead, ContactBirthdayCascadesRead,
                "/organizer/contact-birthday-settings", "/organizer/contact-birthday-settings",
                lambda: {"relationships": BIRTHDAY_CASCADES},
            ),
        ),
    ),
    CatalogNamespace(
        "assistant", "Assistant", "How Alfred addresses you.",
        (CatalogSource(
            AssistantSettingsUpdate, AssistantSettingsRead, "/core/assistant-settings", "/core/assistant-settings",
            lambda: {},
        ),),
    ),
)


def catalog_fields() -> list[tuple[CatalogNamespace, CatalogSource, str, FieldInfo]]:
    """Every field the catalog covers, in page order."""
    return [
        (namespace, source, name, info)
        for namespace in NAMESPACES
        for source in namespace.sources
        for name, info in source.schema.model_fields.items()
        if name not in source.exclude
    ]


def _extra(info: FieldInfo) -> dict[str, Any]:
    extra = info.json_schema_extra
    return dict(extra) if isinstance(extra, dict) else {}


def _value_schema(property_schema: dict[str, Any]) -> dict[str, Any]:
    """The non-null branch of `X | None`."""
    branches = [b for b in property_schema.get("anyOf", []) if b.get("type") != "null"]
    return branches[0] if branches else property_schema


def _nullable(read_schema: type[BaseModel], name: str) -> bool:
    read_field = read_schema.model_fields.get(name)
    if read_field is None:
        return False
    annotation = read_field.annotation
    origin = typing.get_origin(annotation)
    return (origin is typing.Union or origin is types.UnionType) and type(None) in typing.get_args(annotation)


def _options(value_schema: dict[str, Any]) -> list[str] | None:
    if "enum" in value_schema:
        return [str(v) for v in value_schema["enum"]]
    names = value_schema.get("propertyNames", {})
    return [str(v) for v in names["enum"]] if "enum" in names else None


def _field(
    namespace: CatalogNamespace, source: CatalogSource, name: str, info: FieldInfo, defaults: Mapping[str, Any]
) -> SettingFieldRead:
    extra = _extra(info)
    value_schema = _value_schema(source.schema.model_json_schema()["properties"][name])
    value_type = value_schema.get("type", "string")
    return SettingFieldRead(
        key=f"{namespace.namespace}.{extra.get('key', name)}",
        field=name,
        label=info.title or name,
        description=info.description,
        widget=extra.get("widget") or _WIDGET_BY_TYPE.get(value_type, "json"),
        type=value_type,
        options=_options(value_schema),
        min=value_schema.get("minimum"),
        max=value_schema.get("maximum"),
        max_length=value_schema.get("maxLength"),
        step=extra.get("step"),
        nullable=_nullable(source.read_schema, name),
        has_default=name in defaults,
        default=defaults.get(name),
        unit=extra.get("unit"),
        group=extra.get("group"),
        confirm_note=extra.get("confirm_note"),
        href=extra.get("href"),
        read_path=source.read_path,
        write_path=extra.get("write_path", source.write_path),
        entry_field=extra.get("entry_field"),
    )


def build_catalog(stored: Mapping[str, str]) -> SettingsCatalogRead:
    """The catalog, with `stored` (every core.settings row) used only to list the keys no field covers."""
    defaults = {id(source): source.defaults() for namespace in NAMESPACES for source in namespace.sources}
    namespaces = [
        SettingsNamespaceRead(
            namespace=namespace.namespace,
            title=namespace.title,
            description=namespace.description,
            fields=[
                _field(namespace, source, name, info, defaults[id(source)])
                for ns, source, name, info in catalog_fields()
                if ns is namespace
            ],
            links=list(namespace.links),
        )
        for namespace in NAMESPACES
    ]
    covered = {f.key for ns in namespaces for f in ns.fields}
    unregistered = [
        StoredSettingRead(key=key, value=value)
        for key, value in sorted(stored.items())
        if key not in covered and not key.startswith(_PRIVATE_PREFIXES)
    ]
    return SettingsCatalogRead(namespaces=namespaces, unregistered=unregistered)
