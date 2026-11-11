from pydantic import BaseModel, Field


class TravelSettingsRead(BaseModel):
    airport_buffer_min: int
    home_to_airport_min: int
    home_address: str | None = None


class TravelSettingsUpdate(BaseModel):
    airport_buffer_min: int | None = Field(default=None, ge=0, le=600)
    home_to_airport_min: int | None = Field(default=None, ge=0, le=600)
    # Where trips start; used for the home -> airport directions. An empty string clears it.
    home_address: str | None = Field(default=None, max_length=300)
