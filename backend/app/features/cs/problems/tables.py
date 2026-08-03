from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.cs.platforms.tables import Platform

problems_tags = Table(
    "problems_tags",
    Base.metadata,
    Column("problem_id", Integer, ForeignKey("cs.problems.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("cs.tags.id", ondelete="CASCADE"), primary_key=True),
    schema="cs",
)


class CsTag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("name", name="uq_cs_tags_name"),
        {"schema": "cs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    problems: Mapped[list["Problem"]] = relationship(
        "app.features.cs.problems.tables.Problem", secondary=problems_tags, back_populates="tags"
    )


class Problem(Base):
    __tablename__ = "problems"
    __table_args__ = (
        UniqueConstraint("platform_id", "external_id", name="uq_cs_problems_platform_external_id"),
        {"schema": "cs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    platform_id: Mapped[int] = mapped_column(
        ForeignKey("cs.platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    difficulty_raw: Mapped[str | None] = mapped_column(String(50), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tags_raw: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    acceptance_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    solved_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dislikes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    platform: Mapped["Platform"] = relationship("app.features.cs.platforms.tables.Platform")
    tags: Mapped[list["CsTag"]] = relationship(
        "app.features.cs.problems.tables.CsTag", secondary=problems_tags, back_populates="problems"
    )
