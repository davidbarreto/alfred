from pydantic import BaseModel, Field


class ContactBirthdayCascadesRead(BaseModel):
    relationships: dict[str, list[str]]


class ContactBirthdayCascadeUpdate(BaseModel):
    offsets: list[str] = Field(min_length=1)
