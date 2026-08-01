import pytest

from app.integrations.null.storage_provider import NullStorageProvider


class TestNullStorageProvider:

    @pytest.mark.asyncio
    async def test_create_assigns_an_id(self):
        provider = NullStorageProvider()

        record = await provider.create({"title": "Buy milk"})

        assert record["id"]
        assert record["title"] == "Buy milk"

    @pytest.mark.asyncio
    async def test_get_returns_previously_created_record(self):
        provider = NullStorageProvider()
        created = await provider.create({"title": "Buy milk"})

        fetched = await provider.get(created["id"])

        assert fetched == created

    @pytest.mark.asyncio
    async def test_get_unknown_id_returns_bare_record(self):
        provider = NullStorageProvider()

        fetched = await provider.get("missing-id")

        assert fetched == {"id": "missing-id"}

    @pytest.mark.asyncio
    async def test_update_merges_fields(self):
        provider = NullStorageProvider()
        created = await provider.create({"title": "Buy milk"})

        updated = await provider.update(created["id"], {"title": "Buy oat milk"})

        assert updated["title"] == "Buy oat milk"
        assert updated["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_delete_removes_record(self):
        provider = NullStorageProvider()
        created = await provider.create({"title": "Buy milk"})

        await provider.delete(created["id"])

        assert await provider.list() == []

    @pytest.mark.asyncio
    async def test_list_returns_all_created_records(self):
        provider = NullStorageProvider()
        await provider.create({"title": "Buy milk"})
        await provider.create({"title": "Buy eggs"})

        records = await provider.list()

        assert len(records) == 2
