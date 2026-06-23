from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class WeatherForecast(BaseModel):
    temperature_max_c: float
    temperature_min_c: float
    feels_like_max_c: float
    precipitation_probability: int
    wind_speed_max_kmh: float
    description: str
    advice: list[str]


class TaskBriefItem(BaseModel):
    id: int
    title: str
    priority: str
    urgency: str
    deadline: datetime | None
    tags: list[str]
    is_overdue: bool


class EventBriefItem(BaseModel):
    id: int
    title: str
    start_time: str
    end_time: str | None
    location: str | None
    description: str | None
    all_day: bool


class HolidayItem(BaseModel):
    name: str
    local_name: str
    country: str


class BirthdayItem(BaseModel):
    name: str
    days_until: int
    date: date


class MorningBriefing(BaseModel):
    date: date
    tasks: list[TaskBriefItem]
    events: list[EventBriefItem]
    weather: WeatherForecast
    holidays: list[HolidayItem]
    birthdays: list[BirthdayItem]


class FormattedBriefing(BaseModel):
    date: date
    text: str
