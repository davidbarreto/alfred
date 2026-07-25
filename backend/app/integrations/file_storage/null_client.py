class NullFileStorage:
    """No-op FileStorage: discards writes, always reports a cache miss.

    Used where the code is wired up to persist audio (cache, playback-by-ref)
    but we don't want that audio actually hitting disk yet.
    """

    async def save(self, data: bytes, relative_path: str) -> None:
        return None

    async def read(self, relative_path: str) -> bytes | None:
        return None

    async def delete(self, relative_path: str) -> bool:
        return False
