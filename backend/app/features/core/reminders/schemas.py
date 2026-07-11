from datetime import date

from pydantic import BaseModel


class ReminderDigest(BaseModel):
    date: date
    has_content: bool
    text: str
