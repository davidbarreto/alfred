from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AudioConverter(Protocol):
    """Async interface for converting audio between formats.

    Swap the implementation (ffmpeg, a cloud transcoding API, …) without
    touching the chunks service layer.
    """

    async def to_ogg_opus(self, audio: bytes) -> bytes: ...


class FileStorage(Protocol):
    """Async interface for persisting and retrieving opaque byte blobs.

    Swap the implementation (local disk, S3, …) without touching the
    service layer. `read()` returns None when `relative_path` doesn't
    exist — used as a not-found/cache-miss signal by callers.
    """

    async def save(self, data: bytes, relative_path: str) -> None: ...

    async def read(self, relative_path: str) -> bytes | None: ...

    async def delete(self, relative_path: str) -> bool: ...


@dataclass
class PronunciationAnalysis:
    """Structured result of an AI pronunciation analysis (score is 0-100)."""

    transcription: str
    score: float
    summary: str
    strengths: list[str]
    issues: list[str]
    tip: str


@dataclass
class PronunciationAnalysisResult:
    """Parsed analysis plus the raw LLM call metadata, for llm_calls logging."""

    analysis: PronunciationAnalysis
    raw_response: str
    tokens_input: int | None
    tokens_output: int | None


class AudioAnalysisProvider(Protocol):
    """Async interface for AI pronunciation feedback on a recorded attempt.

    Swap the implementation (Google Gemini, …) without touching the
    shadowing service layer.
    """

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def analyze_pronunciation(
        self,
        audio: bytes,
        mime_type: str,
        text: str,
        translation: str | None,
        language_name: str,
    ) -> PronunciationAnalysisResult: ...


@dataclass
class TranscriptionResult:
    """Plain speech-to-text result plus the raw LLM call metadata, for llm_calls logging."""

    text: str
    tokens_input: int | None
    tokens_output: int | None


class TranscriptionProvider(Protocol):
    """Async interface for plain speech-to-text transcription.

    Swap the implementation (Google Gemini, …) without touching the
    transcription service layer.
    """

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionResult: ...
