import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class FfmpegClient:
    """Wraps the ffmpeg binary to convert audio into Telegram-compatible OGG/Opus voice notes."""

    async def to_ogg_opus(self, audio: bytes) -> bytes:
        start = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", "64k",
            "-vbr", "on",
            "-application", "voip",
            "-f", "ogg",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(input=audio)
        if process.returncode != 0:
            logger.error(
                "ffmpeg conversion to ogg/opus failed: returncode=%d stderr=%s",
                process.returncode, stderr.decode(errors="replace")[:500],
            )
            raise RuntimeError(f"ffmpeg exited with code {process.returncode}")

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "Converted audio to ogg/opus: input_bytes=%d output_bytes=%d duration_ms=%d",
            len(audio), len(stdout), duration_ms,
        )
        return stdout
