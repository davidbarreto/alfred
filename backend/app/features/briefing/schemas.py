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
    is_today: bool


class EventBriefItem(BaseModel):
    id: int
    title: str
    date: date
    start_time: str
    end_time: str | None
    location: str | None
    description: str | None
    all_day: bool
    is_today: bool
    days_until: int


class HolidayItem(BaseModel):
    name: str
    local_name: str
    country: str
    days_until: int
    date: date


class BirthdayItem(BaseModel):
    name: str
    days_until: int
    date: date


class LanguageBriefItem(BaseModel):
    track_id: int
    code: str
    name: str
    due_count: int
    completed_today: int
    daily_quota: int
    quota_met: bool


class MorningBriefing(BaseModel):
    date: date
    lookahead_days: int = 1
    tasks: list[TaskBriefItem]
    events: list[EventBriefItem]
    weather: WeatherForecast
    holidays: list[HolidayItem]
    birthdays: list[BirthdayItem]
    language: list[LanguageBriefItem] = []


class FormattedBriefing(BaseModel):
    date: date
    text: str
