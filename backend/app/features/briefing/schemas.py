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


class ShoppingBriefItem(BaseModel):
    id: int
    name: str
    category: str
    priority: str
    quantity: float | None
    unit: str | None
    store: str | None


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
    weather: WeatherForecast | None
    holidays: list[HolidayItem]
    birthdays: list[BirthdayItem]
    language: list[LanguageBriefItem] = []
    shopping: list[ShoppingBriefItem] = []


class WinItem(BaseModel):
    title: str


class EveningTaskItem(BaseModel):
    id: int
    title: str
    priority: str
    urgency: str
    deadline: datetime | None
    tags: list[str]
    is_overdue: bool


class EveningEventItem(BaseModel):
    id: int
    title: str
    date: date
    start_time: str
    end_time: str | None
    location: str | None
    all_day: bool


class EveningNoteItem(BaseModel):
    id: int
    title: str
    content: str


class EveningDigest(BaseModel):
    date: date
    wins: list[WinItem]
    tasks: list[EveningTaskItem]
    tomorrow_events: list[EveningEventItem]
    notes: list[EveningNoteItem]


class FormattedBriefing(BaseModel):
    date: date
    text: str


class BriefingHistoryItem(BaseModel):
    date: date
    type: str
    text: str
