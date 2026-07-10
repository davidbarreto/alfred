from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LearningSession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "language"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("language.tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("language.chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_type: Mapped[str] = mapped_column(String(20), nullable=False)
    task_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    prompt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feeds_srs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audio_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ai_feedback_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transcript_or_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    track: Mapped["Track"] = relationship("Track")
    chunk: Mapped[Optional["Chunk"]] = relationship("Chunk")


from app.features.language.tracks.tables import Track  # noqa: E402
from app.features.language.chunks.tables import Chunk  # noqa: E402
