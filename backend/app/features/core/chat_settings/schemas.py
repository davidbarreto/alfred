from pydantic import BaseModel

from app.features.core.settings.metadata import setting

# The constants the code used before they became chat.* settings. Temperature and the intent values default to
# their env vars (see `defaults()` in the service).
DEFAULT_HISTORY_LIMIT = 10
DEFAULT_MEMORY_LIMIT = 5
DEFAULT_MEMORY_THRESHOLD = 0.6
DEFAULT_RECALL_THRESHOLD = 0.5
DEFAULT_RECALL_LIMIT = 8
DEFAULT_MEMORY_DEDUP_THRESHOLD = 0.85
DEFAULT_MEMORY_IMPORTANCE_BUMP = 0.1


class ChatSettingsRead(BaseModel):
    history_limit: int
    memory_limit: int
    memory_threshold: float
    temperature: float
    recall_threshold: float
    recall_limit: int
    memory_dedup_threshold: float
    memory_importance_bump: float
    intent_threshold: float
    intent_shortlist_floor: float
    intent_shortlist_k: int


class ChatSettingsUpdate(BaseModel):
    """Tuning knobs; a field left out, or null, is untouched. Read on every message, so a change applies at once."""

    history_limit: int | None = setting(
        "Messages of history", "Earlier messages of the conversation sent with each chat reply.",
        unit="messages", group="Chat replies", advanced=True, ge=0, le=50,
    )
    memory_limit: int | None = setting(
        "Memories per reply", "Memories, notes and tasks found by meaning and added to the reply's context.",
        unit="items", group="Chat replies", advanced=True, ge=0, le=20,
    )
    memory_threshold: float | None = setting(
        "Memory match from", "Similarity a memory needs to be added to the context.",
        group="Chat replies", advanced=True, step=0.01, ge=0, le=1,
    )
    temperature: float | None = setting(
        "Temperature", "Higher is more varied, lower more predictable. Falls back to LLM_CHAT_TEMPERATURE.",
        group="Chat replies", advanced=True, step=0.05, ge=0, le=2,
    )
    recall_threshold: float | None = setting(
        "Recall match from", "Similarity a result needs to be returned by recall.",
        group="Recall", advanced=True, step=0.01, ge=0, le=1,
    )
    recall_limit: int | None = setting(
        "Recall results", "", unit="results", group="Recall", advanced=True, ge=1, le=50,
    )
    memory_dedup_threshold: float | None = setting(
        "Same memory from", "An extracted memory this similar to an existing one bumps it instead of being added.",
        group="Memory extraction", advanced=True, step=0.01, ge=0, le=1,
    )
    memory_importance_bump: float | None = setting(
        "Importance bump", "Added to a memory's importance when it comes up again.",
        group="Memory extraction", advanced=True, step=0.01, ge=0, le=1,
    )
    intent_threshold: float | None = setting(
        "Command match from", "An embedding score at or above this runs the command directly. "
        "Falls back to INTENT_THRESHOLD.",
        group="Intent detection", advanced=True, step=0.01, ge=0, le=1,
    )
    intent_shortlist_floor: float | None = setting(
        "Shortlist from", "Between this and the command match, the top intents go to the LLM to pick; below it the "
        "message is plain chat. Falls back to INTENT_SHORTLIST_FLOOR.",
        group="Intent detection", advanced=True, step=0.01, ge=0, le=1,
    )
    intent_shortlist_k: int | None = setting(
        "Shortlist size", "Falls back to INTENT_SHORTLIST_K.",
        unit="intents", group="Intent detection", advanced=True, ge=1, le=20,
    )
