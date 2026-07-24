from pydantic import BaseModel


class ConversationStartCreate(BaseModel):
    track_id: int
    message_id: int
    scenario: str
    voice_reply: bool = False


class ConversationStartRead(BaseModel):
    thread_id: int
    track_code: str
    language_name: str
    opening_text: str
    opening_audio_ref: str | None = None


class ConversationTurnResultRead(BaseModel):
    """`response` mirrors ChatAudioResponse's field name so n8n's existing Send Message
    node (bound to `{{$json.response}}`) works for both tiers with no extra mapping step."""
    response: str
    reply_audio_base64: str | None = None
    tip: str | None = None


class ConversationEndRead(BaseModel):
    tip: str | None = None
    turn_count: int
