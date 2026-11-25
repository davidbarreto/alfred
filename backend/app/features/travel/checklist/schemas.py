from pydantic import BaseModel, Field, model_validator

from app.features.core.settings.metadata import setting
from app.features.travel.checklist.template import SLUG_PATTERN, Anchor

MAX_ITEMS = 50
# Signed: negative = before the anchor date, 0 = the anchor day, positive = after it.
_OFFSET_LIMIT = 3650


class ChecklistItemRead(BaseModel):
    anchor: Anchor
    name: str
    title: str
    offset_days: int


class ChecklistItemWrite(BaseModel):
    anchor: Anchor
    name: str = Field(pattern=SLUG_PATTERN.pattern, max_length=60)
    offset_days: int = Field(ge=-_OFFSET_LIMIT, le=_OFFSET_LIMIT)


class ChecklistTemplateRead(BaseModel):
    items: list[ChecklistItemRead]


class ChecklistTemplateUpdate(BaseModel):
    """The whole template: items left out are deleted."""

    items: list[ChecklistItemWrite] = setting(
        "Pre-trip checklist",
        "Each item becomes a task when you press \"Generate checklist\" on a trip, due its days from the trip's start "
        "or end (negative = before).",
        widget="checklist", key="checklist", group="Pre-trip checklist", default=..., max_length=MAX_ITEMS,
    )

    @model_validator(mode="after")
    def _unique_names(self) -> "ChecklistTemplateUpdate":
        names = [item.name for item in self.items]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"names must be unique across both groups: {', '.join(duplicates)}")
        return self


class ChecklistGenerated(BaseModel):
    created: list[str]
    skipped: list[str]
