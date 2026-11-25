from pydantic import BaseModel

from app.features.core.settings.metadata import setting

# The constants the import used before they became finance.* settings.
DEFAULT_IMPORT_KNN_LIMIT = 7
DEFAULT_IMPORT_KNN_THRESHOLD = 0.72
DEFAULT_IMPORT_KNN_MIN_VOTE = 0.7


class FinanceSettingsRead(BaseModel):
    cycle_start_day: int
    import_knn_limit: int = DEFAULT_IMPORT_KNN_LIMIT
    import_knn_threshold: float = DEFAULT_IMPORT_KNN_THRESHOLD
    import_knn_min_vote: float = DEFAULT_IMPORT_KNN_MIN_VOTE


class FinanceSettingsUpdate(BaseModel):
    """Partial update: a field left out, or null, is untouched."""

    cycle_start_day: int | None = setting(
        "Cycle start day",
        "The day of the month your finance cycle starts (e.g. payday). Budgets and monthly totals count from it.",
        unit="day of month",
        ge=1,
        le=28,
    )
    import_knn_limit: int | None = setting(
        "Similar past transactions", "How many past transactions vote on an imported row's category.",
        unit="transactions", group="Statement import matching", advanced=True, ge=1, le=50,
    )
    import_knn_threshold: float | None = setting(
        "Similar from", "Similarity a past transaction needs to vote.",
        group="Statement import matching", advanced=True, step=0.01, ge=0, le=1,
    )
    import_knn_min_vote: float | None = setting(
        "Suggest a category from", "Share of the votes a category needs to be suggested.",
        group="Statement import matching", advanced=True, step=0.01, ge=0, le=1,
    )
