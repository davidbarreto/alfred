from pydantic import BaseModel

from app.features.core.settings.metadata import setting

# The constants the weak-tag ranking used before they became cs.* settings.
DEFAULT_WEAK_TAG_MIN_ATTEMPTS = 3
DEFAULT_WEAK_TAG_MAX_SOLVE_RATE = 0.85
DEFAULT_WEAK_TAGS_SHOWN = 5


class CsSettingsRead(BaseModel):
    weak_tag_min_attempts: int = DEFAULT_WEAK_TAG_MIN_ATTEMPTS
    weak_tag_max_solve_rate: float = DEFAULT_WEAK_TAG_MAX_SOLVE_RATE
    weak_tags_shown: int = DEFAULT_WEAK_TAGS_SHOWN


class CsSettingsUpdate(BaseModel):
    """Tuning knobs; a field left out, or null, is untouched."""

    weak_tag_min_attempts: int | None = setting(
        "Weak tag needs at least", "Attempts a tag needs before it can count as weak.",
        unit="attempts", group="Weak tags", advanced=True, ge=1, le=100,
    )
    weak_tag_max_solve_rate: float | None = setting(
        "Weak below solve rate", "A tag solved at least this often is never called weak.",
        group="Weak tags", advanced=True, step=0.01, ge=0, le=1,
    )
    weak_tags_shown: int | None = setting(
        "Weak tags listed", "", unit="tags", group="Weak tags", advanced=True, ge=1, le=20,
    )
