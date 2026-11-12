from pydantic import BaseModel, Field

from app.features.travel.checklist.template import Anchor


class ChecklistItemRead(BaseModel):
    anchor: Anchor
    name: str
    title: str
    offset_days: int


class ChecklistItemWrite(BaseModel):
    # Signed: negative = before the anchor date, 0 = the anchor day, positive = after it.
    offset_days: int = Field(ge=-3650, le=3650)


class ChecklistGenerated(BaseModel):
    created: list[str]
    skipped: list[str]
