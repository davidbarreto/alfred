from pydantic import BaseModel

from app.features.core.settings.metadata import setting

# The constants the stats used before they became metrics.* settings.
DEFAULT_TREND_DAYS = 30
DEFAULT_MIN_SAMPLES = 5


class MetricsSettingsRead(BaseModel):
    trend_days: int = DEFAULT_TREND_DAYS
    min_samples: int = DEFAULT_MIN_SAMPLES


class MetricsSettingsUpdate(BaseModel):
    """Tuning knobs; a field left out, or null, is untouched."""

    trend_days: int | None = setting(
        "Trend window", "Recent days compared with the same number of days before them.",
        unit="days", group="Stats", advanced=True, ge=7, le=365,
    )
    min_samples: int | None = setting(
        "Samples for a reliable group", "A group with fewer entries is flagged and never ranked best.",
        unit="entries", group="Stats", advanced=True, ge=1, le=100,
    )
