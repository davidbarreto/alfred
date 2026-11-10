from pydantic import BaseModel, Field


class TravelSettingsRead(BaseModel):
    airport_buffer_min: int
    home_to_airport_min: int


class TravelSettingsUpdate(BaseModel):
    airport_buffer_min: int | None = Field(default=None, ge=0, le=600)
    home_to_airport_min: int | None = Field(default=None, ge=0, le=600)
