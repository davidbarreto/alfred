import logging
from typing import Literal

from app.shared.audio import AudioConverter
from app.shared.pronunciation import PronunciationProvider

logger = logging.getLogger(__name__)

AudioFormat = Literal["mp3", "ogg"]
_CONTENT_TYPES: dict[str, str] = {"mp3": "audio/mpeg", "ogg": "audio/ogg"}


class PronunciationService:

    def __init__(self, client: PronunciationProvider, converter: AudioConverter) -> None:
        self._client = client
        self._converter = converter

    async def get_audio(self, text: str, lang: str, audio_format: AudioFormat = "mp3") -> tuple[bytes, str]:
        audio = await self._client.get_audio(text, lang)
        logger.debug("Pronunciation audio fetched: lang=%s text_len=%d format=%s", lang, len(text), audio_format)

        if audio_format == "ogg":
            audio = await self._converter.to_ogg_opus(audio)

        return audio, _CONTENT_TYPES[audio_format]
