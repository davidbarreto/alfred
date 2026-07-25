from typing import Literal

from pydantic import BaseModel

ConversationMode = Literal["roleplay", "conversation"]


class ConversationStartCreate(BaseModel):
    track_id: int
    message_id: int
    mode: ConversationMode = "roleplay"
    # Roleplay scenario or free-conversation topic; optional for a topic-less chat.
    scenario: str | None = None
    voice_reply: bool = False


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
