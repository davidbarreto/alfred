from pydantic import BaseModel

from app.features.core.settings.metadata import setting


class FinanceSettingsRead(BaseModel):
    cycle_start_day: int


class FinanceSettingsUpdate(BaseModel):
    cycle_start_day: int = setting(
        "Cycle start day",
        "The day of the month your finance cycle starts (e.g. payday). Budgets and monthly totals count from it.",
        unit="day of month",
        default=...,
        ge=1,
        le=28,
    )
