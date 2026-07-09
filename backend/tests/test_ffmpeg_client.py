from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.ffmpeg.client import FfmpegClient


def _mock_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    process = AsyncMock()
    process.communicate.return_value = (stdout, stderr)
    process.returncode = returncode
    return process


class TestToOggOpus:

    @pytest.mark.asyncio
    async def test_returns_converted_audio_on_success(self):
        client = FfmpegClient()
        process = _mock_process(stdout=b"fake-ogg-bytes")

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as mock_exec:
            result = await client.to_ogg_opus(b"fake-mp3-bytes")

        assert result == b"fake-ogg-bytes"
        process.communicate.assert_awaited_once_with(input=b"fake-mp3-bytes")
        call_args = mock_exec.call_args.args
        assert call_args[0] == "ffmpeg"
        assert "libopus" in call_args

    @pytest.mark.asyncio
    async def test_raises_when_ffmpeg_exits_nonzero(self):
        client = FfmpegClient()
        process = _mock_process(stderr=b"invalid data found", returncode=1)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
            with pytest.raises(RuntimeError, match="ffmpeg exited with code 1"):
                await client.to_ogg_opus(b"not-audio")
