from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.features.location.places.schemas import PlaceRef

# Total travel times across all places; each one is ~10 tokens in a day plan.
MAX_TRAVEL_TIMES = 60


class TravelTimeSet(BaseModel):
    """Minutes from the place in the path to `destination_id` by `mode`; saving the same route again updates it."""

    destination_id: int
    mode: str = Field(min_length=1, max_length=40)
    minutes: int = Field(ge=1, le=600)

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        cleaned = " ".join(value.split()).lower()
        if not cleaned:
            raise ValueError("mode must not be blank")
        return cleaned


class TravelTimeRead(BaseModel):
    id: int
    origin: PlaceRef
    destination: PlaceRef
    mode: str
    minutes: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
