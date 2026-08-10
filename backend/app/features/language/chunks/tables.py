from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Alfred has no external write-through provider for chunks and is single-tenant,
# so unlike organizer.tags, tag names here are just globally unique (no provider_id
# scoping column).
chunks_tags = Table(
    "chunks_tags",
    Base.metadata,
    Column("chunk_id", Integer, ForeignKey("language.chunks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("language.tags.id", ondelete="CASCADE"), primary_key=True),
    schema="language",
)


class LanguageTag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("name", name="uq_language_tags_name"),
        {"schema": "language"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", secondary=chunks_tags, back_populates="tags"
    )


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
    first_reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="new")

    # FSRS-5 production fields (independent track; prod_due_at is NULL until the
    # chunk is unlocked by a first successful recognition review)
    prod_stability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prod_difficulty: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    prod_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    prod_last_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    prod_repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prod_lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prod_consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prod_state: Mapped[str] = mapped_column(String(20), nullable=False, default="new")

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
    # eager (not the codebase's usual per-query selectinload) because Chunk is read from
    # many call sites across services/repositories, and ChunkRead always serializes tags
    tags: Mapped[list["LanguageTag"]] = relationship(
        "LanguageTag", secondary=chunks_tags, back_populates="chunks", lazy="selectin"
    )


from app.features.language.tracks.tables import Track  # noqa: E402
from app.features.language.grammar_scope.tables import GrammarScope  # noqa: E402
