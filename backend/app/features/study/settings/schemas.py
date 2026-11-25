from pydantic import BaseModel

from app.features.core.settings.metadata import setting


class StudySettingsRead(BaseModel):
    max_active_plans: int


class StudySettingsUpdate(BaseModel):
    max_active_plans: int = setting(
        "Active plans at most",
        "How many study plans can be active at once, over every subject. A new plan beyond it is refused.",
        unit="plans",
        default=...,
        ge=1,
        le=10,
    )
