import pytest

from app.integrations.file_storage.null_client import NullFileStorage


class TestNullFileStorage:

    @pytest.mark.asyncio
    async def test_save_is_a_noop(self):
        storage = NullFileStorage()

        result = await storage.save(b"hello world", "conversation/turn.ogg")

        assert result is None

    @pytest.mark.asyncio
    async def test_read_always_reports_a_miss(self):
        storage = NullFileStorage()
        await storage.save(b"hello world", "conversation/turn.ogg")

        result = await storage.read("conversation/turn.ogg")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_always_reports_nothing_to_delete(self):
        storage = NullFileStorage()

        result = await storage.delete("conversation/turn.ogg")

        assert result is False
