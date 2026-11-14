from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator


def normalize_tags(tags: list[str] | None) -> list[str] | None:
    """Trim, lowercase, drop blanks and duplicates, enforce the length cap. Tags are stored lowercase."""
    if tags is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = tag.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        if len(cleaned) > 100:
            raise ValueError("tags must be at most 100 characters")
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


class TravelTagRead(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class TravelTagUsage(BaseModel):
    id: int
    name: str
    trip_count: int
    place_count: int = 0


class TravelTagUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

    @field_validator("name")
    @classmethod
    def _lowercase_name(cls, value: str) -> str:
        return value.lower()
