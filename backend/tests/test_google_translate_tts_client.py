from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.google_translate_tts.client import GoogleTranslateTtsClient


def _mock_response(content: bytes = b"", status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    resp.raise_for_status.side_effect = (
        httpx.HTTPStatusError("error", request=MagicMock(), response=resp) if status_code >= 400 else None
    )
    return resp


class TestGetAudio:

    @pytest.mark.asyncio
    async def test_returns_audio_bytes(self):
        client = GoogleTranslateTtsClient()

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=_mock_response(b"fake-mp3-bytes")
            )
            result = await client.get_audio("bonjour", "fr")

        assert result == b"fake-mp3-bytes"

    @pytest.mark.asyncio
    async def test_sends_text_and_lang_as_params(self):
        client = GoogleTranslateTtsClient()

        with patch("httpx.AsyncClient") as mock_http:
            mock_get = AsyncMock(return_value=_mock_response(b"audio"))
            mock_http.return_value.__aenter__.return_value.get = mock_get
            await client.get_audio("hola", "es")

        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["params"]["q"] == "hola"
        assert call_kwargs["params"]["tl"] == "es"

    @pytest.mark.asyncio
    async def test_raises_on_error_response(self):
        client = GoogleTranslateTtsClient()

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=_mock_response(status_code=500)
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_audio("bonjour", "fr")
