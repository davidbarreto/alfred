from __future__ import annotations

from typing import Protocol


class AudioConverter(Protocol):
    """Async interface for converting audio between formats.

    Swap the implementation (ffmpeg, a cloud transcoding API, …) without
    touching the chunks service layer.
    """

    async def to_ogg_opus(self, audio: bytes) -> bytes: ...
