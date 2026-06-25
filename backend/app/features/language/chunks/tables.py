from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = {"schema": "language"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("language.tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grammar_scope_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("language.grammar_scope.id", ondelete="SET NULL"), nullable=True, index=True
    )

    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    translation: Mapped[str] = mapped_column(String(500), nullable=False)
    example_sentence: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    example_translation: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    cefr_level: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    frequency_source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # FSRS-5 fields
    stability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    last_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="new")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_triage")
    is_leech: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    track: Mapped["Track"] = relationship("Track")
    grammar_scope: Mapped[Optional["GrammarScope"]] = relationship("GrammarScope")


from app.features.language.tracks.tables import Track  # noqa: E402
from app.features.language.grammar_scope.tables import GrammarScope  # noqa: E402
