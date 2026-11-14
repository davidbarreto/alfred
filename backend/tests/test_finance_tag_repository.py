import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.tags.repository import TagRepository
from app.features.finance.tags.schemas import TagCreate, TagUpdate


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _make_tag_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.name = kwargs.get("name", "Travel")
    return t


class TestGetTag:
    async def test_found(self):
        session = _make_session()
        tag = _make_tag_orm()
        session.execute.return_value = _scalar_first(tag)
        assert await TagRepository(session).get_tag(1) == tag

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await TagRepository(session).get_tag(999) is None


class TestGetTags:
    async def test_returns_all(self):
        session = _make_session()
        tags = [_make_tag_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(tags)
        result = await TagRepository(session).get_tags()
        assert len(result) == 3

    async def test_empty(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        assert await TagRepository(session).get_tags() == []


class TestResolveTags:
    async def test_reuses_existing_tag_by_name(self):
        session = _make_session()
        existing = _make_tag_orm(id=1, name="Travel")
        session.execute.return_value = _scalar_first(existing)
        result = await TagRepository(session).resolve_tags(["Travel"])
        assert result == [existing]
        session.add.assert_not_called()

    async def test_creates_new_tag_when_missing(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TagRepository(session).resolve_tags(["Work"])
        assert len(result) == 1
        assert result[0].name == "work"
        session.add.assert_called_once()

    async def test_lookup_is_case_insensitive(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(_make_tag_orm(name="Travel"))
        await TagRepository(session).resolve_tags(["TRAVEL"])
        sql = str(session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "lower(finance.tags.name) = 'travel'" in sql

    async def test_same_name_in_different_case_resolves_to_one_tag(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TagRepository(session).resolve_tags(["Rome", "rome", "ROME"])
        assert len(result) == 1
        assert result[0].name == "rome"
        session.add.assert_called_once()

    async def test_empty_names_returns_empty_list(self):
        session = _make_session()
        result = await TagRepository(session).resolve_tags([])
        assert result == []
        session.execute.assert_not_called()


class TestGetTagByName:
    async def test_matches_ignoring_case(self):
        session = _make_session()
        tag = _make_tag_orm()
        session.execute.return_value = _scalar_first(tag)
        assert await TagRepository(session).get_tag_by_name(" TRAVEL ") == tag
        sql = str(session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "lower(finance.tags.name) = 'travel'" in sql

    async def test_exclude_id_leaves_out_that_tag(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        await TagRepository(session).get_tag_by_name("Travel", exclude_id=3)
        sql = str(session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "finance.tags.id != 3" in sql


class TestCreateTag:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        await TagRepository(session).create_tag(TagCreate(name="Travel"))
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestUpdateTag:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TagRepository(session).update_tag(999, TagUpdate(name="X"))
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_field_and_commits(self):
        session = _make_session()
        tag = _make_tag_orm()
        session.execute.return_value = _scalar_first(tag)
        await TagRepository(session).update_tag(1, TagUpdate(name="Business"))
        session.commit.assert_called_once()


class TestDeleteTag:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await TagRepository(session).delete_tag(999) is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        tag = _make_tag_orm()
        session.execute.return_value = _scalar_first(tag)
        result = await TagRepository(session).delete_tag(1)
        assert result is True
        session.delete.assert_called_once_with(tag)
        session.commit.assert_called_once()

    async def test_rolls_back_and_reraises_on_integrity_error(self):
        session = _make_session()
        tag = _make_tag_orm()
        session.execute.return_value = _scalar_first(tag)
        session.commit.side_effect = IntegrityError("", "", Exception("fk violation"))
        with pytest.raises(IntegrityError):
            await TagRepository(session).delete_tag(1)
        session.rollback.assert_called_once()
