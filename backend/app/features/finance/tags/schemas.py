from pydantic import BaseModel


class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = None


class TagRead(TagBase):
    id: int

    model_config = {"from_attributes": True}
