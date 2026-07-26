from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationThread(Base):
    __tablename__ = "conversation_threads"
    __table_args__ = {"schema": "language"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("language.tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chat_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("core.sessions.id", ondelete="CASCADE"), nullable=False
    )
    # "roleplay" (scripted scenario) or "conversation" (free chat on an optional topic).
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="roleplay")
    # The roleplay scenario or the free-conversation topic; absent for a topic-less chat.
    scenario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voice_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Punctual CEFR override for this session only (e.g. "A0"); never written back to
    # tracks.level. Falls back to the track's own level when unset.
    level_override: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tip: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    __table_args__ = {"schema": "language"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    thread_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("language.conversation_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("core.messages.id", ondelete="CASCADE"), nullable=False
    )
    is_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audio_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tip: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
