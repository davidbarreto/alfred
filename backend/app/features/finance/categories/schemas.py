from pydantic import BaseModel


class CategoryBase(BaseModel):
    name: str
    parent_id: int | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None


class CategoryRead(CategoryBase):
    id: int

    model_config = {"from_attributes": True}
