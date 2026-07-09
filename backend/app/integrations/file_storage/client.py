import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalFileStorage:
    """Stores byte blobs on the local filesystem, rooted at `base_dir`."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)

    def _resolve(self, relative_path: str) -> Path:
        return self._base_dir / relative_path

    async def save(self, data: bytes, relative_path: str) -> None:
        path = self._resolve(relative_path)
        await asyncio.to_thread(self._write, path, data)
        logger.debug("File saved: path=%s bytes=%d", relative_path, len(data))

    async def read(self, relative_path: str) -> bytes | None:
        path = self._resolve(relative_path)
        if not await asyncio.to_thread(path.exists):
            return None
        return await asyncio.to_thread(path.read_bytes)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
