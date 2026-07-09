from __future__ import annotations

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
