from typing import Annotated, Optional

from fastapi import Query
from pydantic import BaseModel, Field

from app.features.location.places.schemas import PlaceCreate, PlaceRead, parse_kind


class PlaceCategory(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class PlaceCategoriesUpdate(BaseModel):
    category_ids: list[int]


class EverydayPlaceCreate(PlaceCreate):
    """A new place that is one of the everyday places from the start, with what it sells."""

    category_ids: list[int] = Field(default_factory=list)


class EverydayPlaceRead(PlaceRead):
    """A place as the everyday role sees it: whether it is everyday (Home always is) and what it sells."""

    everyday: bool
    categories: list[PlaceCategory] = Field(default_factory=list)


class EverydayPlaceFilters:
    def __init__(
        self,
        kind: Annotated[Optional[str], Query()] = None,
        active: Annotated[Optional[bool], Query()] = None,
        category_id: Annotated[Optional[int], Query(description="Only places that sell this shopping category")] = None,
        city_id: Annotated[Optional[int], Query(description="Only places in this city")] = None,
        q: Annotated[Optional[str], Query(description="Substring of the name or address")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.kind = parse_kind(kind)
        self.active = active
        self.category_id = category_id
        self.city_id = city_id
        self.q = q.strip() if q and q.strip() else None
        self.limit = limit
        self.offset = offset

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EverydayPlaceFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"EverydayPlaceFilters({vars(self)!r})"
