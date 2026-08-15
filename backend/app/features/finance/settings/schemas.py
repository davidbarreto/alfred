from pydantic import BaseModel, Field


class FinanceSettingsRead(BaseModel):
    cycle_start_day: int


class FinanceSettingsUpdate(BaseModel):
    cycle_start_day: int = Field(ge=1, le=28)
