from datetime import datetime
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict

ConversationMode = Literal["roleplay", "conversation"]


class ConversationStartCreate(BaseModel):
    track_id: int
    message_id: int
    mode: ConversationMode = "roleplay"
    # Roleplay scenario or free-conversation topic; optional for a topic-less chat.
    scenario: str | None = None
    voice_reply: bool = False
    # Punctual CEFR override for this session only (e.g. "A0"); falls back to the track's
    # own level when unset. Never written back to the track.
    level_override: str | None = None


class ConversationStartRead(BaseModel):
    thread_id: int
    track_code: str
    language_name: str
    # Only roleplay opens with a line; free conversation waits for the user to speak first.
    opening_text: str | None = None
    opening_audio_ref: str | None = None


class ConversationTextTurnCreate(BaseModel):
    thread_id: int
    text: str


class ConversationTurnResultRead(BaseModel):
    """`response` mirrors ChatResponse's field name so n8n's existing Send Message node
    (bound to `{{$json.response}}`) works here too with no extra mapping step."""
    response: str
    reply_audio_base64: str | None = None
    tip: str | None = None


class ConversationEndRead(BaseModel):
    tip: str | None = None
    turn_count: int


class ConversationThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    track_id: int
    chat_session_id: int
    mode: str
    scenario: str | None
    voice_reply: bool
    level_override: str | None
    started_at: datetime
    ended_at: datetime | None
    tip: str | None


class ConversationTurnRead(BaseModel):
    """A turn plus the message text it points at, so the portal can render the
    exchange and its coaching tips without a second round trip."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    message_id: int
    role: str
    content: str
    is_audio: bool
    audio_ref: str | None
    tip: str | None
    created_at: datetime


class ConversationThreadFilters:
    def __init__(
        self,
        track_id: Annotated[int | None, Query()] = None,
        mode: Annotated[ConversationMode | None, Query()] = None,
        active_only: Annotated[bool, Query()] = False,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.track_id = track_id
        self.mode = mode
        self.active_only = active_only
        self.limit = limit
        self.offset = offset
