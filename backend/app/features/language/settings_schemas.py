from pydantic import BaseModel

from app.features.core.settings.metadata import setting
from app.features.language.srs import DEFAULT_LEECH_THRESHOLD, DEFAULT_REQUESTED_RETENTION

DEFAULT_TIMED_TASK_SECONDS = 300


class LanguageSettingsRead(BaseModel):
    requested_retention: float = DEFAULT_REQUESTED_RETENTION
    leech_threshold: int = DEFAULT_LEECH_THRESHOLD
    timed_task_seconds: int = DEFAULT_TIMED_TASK_SECONDS


class LanguageSettingsUpdate(BaseModel):
    """Global, not per track. A field left out, or null, is untouched."""

    requested_retention: float | None = setting(
        "Requested retention",
        "The recall probability review intervals aim for: higher means more reviews, shorter intervals. "
        "Only intervals from the next review on change; due dates already set are not recomputed.",
        group="Reviews", step=0.01, ge=0.70, le=0.97,
    )
    leech_threshold: int | None = setting(
        "Leech after", "A card failed this many times in a row is flagged as a leech.",
        unit="failures in a row", group="Reviews", ge=2, le=50,
    )
    timed_task_seconds: int | None = setting(
        "Timed writing task", "How long a timed writing task lasts.",
        unit="s", group="Production", step=30, ge=60, le=3600,
    )
