from pydantic import BaseModel

from app.features.language.sessions.schemas import NextPracticePrompt


class ChatRequest(BaseModel):
    session_id: int
    detected_intents: list[str] | None = None


class ChatResponse(BaseModel):
    response: str
    source: str | None = None
    external_id: str | None = None
    next_practice: NextPracticePrompt | None = None


class ChatAudioResponse(BaseModel):
    response: str
    reply_audio_base64: str | None = None
