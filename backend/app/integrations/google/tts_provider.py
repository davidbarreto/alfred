from __future__ import annotations

import io
import logging
import wave

from google import genai
from google.genai import types

from app.shared.pronunciation import TtsAudioResult

logger = logging.getLogger(__name__)

_SAMPLE_RATE_HZ = 24000
_SAMPLE_WIDTH_BYTES = 2
_CHANNELS = 1


class TtsSynthesisError(RuntimeError):
    """Raised when Gemini TTS returns no audio content. Carries finish_reason (when
    available) so callers can log it alongside the failed call, e.g. to llm_calls."""

    def __init__(self, message: str, finish_reason: str | None = None) -> None:
        super().__init__(message)
        self.finish_reason = finish_reason


def _wrap_pcm_as_wav(pcm: bytes) -> bytes:
    """Gemini TTS returns headerless 16-bit/24kHz/mono PCM; wrap it in a WAV
    container so downstream ffmpeg conversion can decode it directly."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(_CHANNELS)
        wav_file.setsampwidth(_SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(_SAMPLE_RATE_HZ)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


class GoogleTtsProvider:
    """PronunciationProvider implementation backed by Gemini's native TTS via google-genai SDK."""

    def __init__(self, api_key: str, model_name: str, voice_name: str) -> None:
        self._model_name = model_name
        self._voice_name = voice_name
        self._client = genai.Client(api_key=api_key)

    @property
    def provider(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._model_name

    async def get_audio(self, text: str, lang: str) -> TtsAudioResult:
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice_name)
                    )
                ),
            ),
        )
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            # Seen with no explicit API error: the model apparently tried to respond to the
            # text as a chat prompt instead of voicing it, and the candidate comes back empty
            # rather than raising. finish_reason/prompt_feedback carry the closest thing to why.
            finish_reason = (
                str(candidate.finish_reason.name) if candidate and candidate.finish_reason else None
            )
            logger.error(
                "Gemini TTS returned no content: lang=%s text_len=%d finish_reason=%s prompt_feedback=%s",
                lang, len(text), finish_reason, response.prompt_feedback,
            )
            raise TtsSynthesisError("Gemini TTS returned no audio content", finish_reason=finish_reason)
        pcm = candidate.content.parts[0].inline_data.data
        logger.debug(
            "Gemini TTS synthesized: lang=%s voice=%s text_len=%d pcm_bytes=%d",
            lang, self._voice_name, len(text), len(pcm),
        )
        usage = response.usage_metadata
        finish_reason = str(candidate.finish_reason.name) if candidate.finish_reason else None
        return TtsAudioResult(
            audio=_wrap_pcm_as_wav(pcm),
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
            finish_reason=finish_reason,
        )
