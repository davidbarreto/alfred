from pydantic import BaseModel


class ShoppingCategoryBase(BaseModel):
    name: str


class ShoppingCategoryCreate(ShoppingCategoryBase):
    pass


class ShoppingCategoryUpdate(BaseModel):
    name: str | None = None


class ShoppingCategoryRead(ShoppingCategoryBase):
    id: int

    model_config = {"from_attributes": True}
