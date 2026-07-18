from pydantic import BaseModel, field_validator


class CurrencyBase(BaseModel):
    code: str
    symbol: str | None = None
    name: str | None = None

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class CurrencyCreate(CurrencyBase):
    pass


class CurrencyUpdate(BaseModel):
    symbol: str | None = None
    name: str | None = None


class CurrencyRead(CurrencyBase):
    model_config = {"from_attributes": True}
