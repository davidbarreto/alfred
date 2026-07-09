import logging

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://translate.google.com/translate_tts"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class GoogleTranslateTtsClient:
    async def get_audio(self, text: str, lang: str) -> bytes:
        params = {"ie": "UTF-8", "client": "tw-ob", "q": text, "tl": lang}
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                _BASE_URL, params=params, headers={"User-Agent": _USER_AGENT}, timeout=10.0
            )
            if resp.is_error:
                logger.error("Google Translate TTS error %s: text=%r lang=%s", resp.status_code, text, lang)
                resp.raise_for_status()
            return resp.content
