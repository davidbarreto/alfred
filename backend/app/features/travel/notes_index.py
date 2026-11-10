"""Embeddings for the free-text `notes` columns, so `recall` can answer "what did I say about Restaurant X".

Each notes column has its own source type in core.embeddings (a derived index; rebuildable). The indexed
text is prefixed with a short label so a hit says what the note belongs to."""
import logging

from app.features.core.embeddings.schemas import EmbeddingCreate
from app.features.core.embeddings.service import EmbeddingService

logger = logging.getLogger(__name__)

TRIP_NOTE = "trip_note"
LEG_NOTE = "leg_note"
STAY_NOTE = "stay_note"
VISIT_NOTE = "visit_note"
PLACE_NOTE = "place_note"
NOTE_SOURCE_TYPES = (TRIP_NOTE, LEG_NOTE, STAY_NOTE, VISIT_NOTE, PLACE_NOTE)


def note_text(label: str, notes: str) -> str:
    return f"{label}: {notes.strip()}"


class TravelNoteIndex:
    """No-op without an embedding service (tests, jobs that never index)."""

    def __init__(self, embedding_service: EmbeddingService | None):
        self._embeddings = embedding_service

    async def sync(self, source_type: str, source_id: int, label: str, notes: str | None) -> None:
        """Index the notes, or drop the embedding when they were cleared."""
        if self._embeddings is None:
            return
        if notes and notes.strip():
            self._embeddings.embed_background(
                EmbeddingCreate(source_type=source_type, source_id=source_id, content=note_text(label, notes))
            )
        else:
            await self.remove(source_type, source_id)

    async def remove(self, source_type: str, source_id: int) -> None:
        if self._embeddings is None:
            return
        try:
            await self._embeddings.delete_by_source(source_type, source_id)
        except Exception as exc:  # the index is derived data: never fail the user's write over it
            logger.warning("Travel note embedding cleanup failed: type=%s id=%d error=%s", source_type, source_id, exc)
