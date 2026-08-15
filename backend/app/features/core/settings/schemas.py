from datetime import datetime
from pydantic import BaseModel


class SettingRead(BaseModel):
    key: str
    value: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingSet(BaseModel):
    value: str
