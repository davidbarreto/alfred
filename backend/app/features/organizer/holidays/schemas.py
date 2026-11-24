from datetime import date

from pydantic import BaseModel


class HolidayRead(BaseModel):
    date: date
    name: str
    # The HOLIDAY_CALENDARS code of the calendar it comes from (e.g. PT).
    country: str
