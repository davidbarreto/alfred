import hashlib
import logging
from typing import Literal

from app.shared.audio import AudioConverter, FileStorage
from app.shared.pronunciation import PronunciationProvider

logger = logging.getLogger(__name__)

AudioFormat = Literal["mp3", "ogg"]
_CONTENT_TYPES: dict[str, str] = {"mp3": "audio/mpeg", "ogg": "audio/ogg"}


def _cache_key(text: str, lang: str, audio_format: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return f"pronunciation_cache/{lang}/{digest}.{audio_format}"


class PronunciationService:

    def __init__(self, client: PronunciationProvider, converter: AudioConverter, storage: FileStorage) -> None:
        self._client = client
        self._converter = converter
        self._storage = storage

    async def get_audio(self, text: str, lang: str, audio_format: AudioFormat = "mp3") -> tuple[bytes, str]:
        cache_key = _cache_key(text, lang, audio_format)
        cached = await self._storage.read(cache_key)
        if cached is not None:
            logger.debug("Pronunciation audio cache hit: lang=%s format=%s", lang, audio_format)
            return cached, _CONTENT_TYPES[audio_format]

        audio = await self._client.get_audio(text, lang)
        logger.debug("Pronunciation audio fetched: lang=%s text_len=%d format=%s", lang, len(text), audio_format)

        if audio_format == "ogg":
            audio = await self._converter.to_ogg_opus(audio)

        await self._storage.save(audio, cache_key)
        return audio, _CONTENT_TYPES[audio_format]
