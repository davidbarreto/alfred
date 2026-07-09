import pytest

from app.integrations.file_storage.client import LocalFileStorage


class TestSaveAndRead:

    @pytest.mark.asyncio
    async def test_read_returns_none_when_missing(self, tmp_path):
        storage = LocalFileStorage(str(tmp_path))

        result = await storage.read("does/not/exist.bin")

        assert result is None

    @pytest.mark.asyncio
    async def test_save_then_read_round_trips(self, tmp_path):
        storage = LocalFileStorage(str(tmp_path))

        await storage.save(b"hello world", "sub/dir/file.bin")
        result = await storage.read("sub/dir/file.bin")

        assert result == b"hello world"

    @pytest.mark.asyncio
    async def test_save_creates_parent_directories(self, tmp_path):
        storage = LocalFileStorage(str(tmp_path))

        await storage.save(b"data", "a/b/c/file.bin")

        assert (tmp_path / "a" / "b" / "c" / "file.bin").read_bytes() == b"data"
