from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.repository import SettingRepository
from app.features.core.settings.tables import Setting


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


class TestGet:
    async def test_returns_setting_when_found(self):
        session = _make_session()
        setting = Setting(key="finance.cycle_start_day", value="25")
        result = MagicMock()
        result.scalars.return_value.first.return_value = setting
        session.execute.return_value = result
        repo = SettingRepository(session)

        found = await repo.get("finance.cycle_start_day")

        assert found is setting

    async def test_returns_none_when_missing(self):
        session = _make_session()
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        session.execute.return_value = result
        repo = SettingRepository(session)

        found = await repo.get("missing.key")

        assert found is None


class TestSet:
    async def test_upserts_and_commits(self):
        session = _make_session()
        setting = Setting(key="finance.cycle_start_day", value="25")
        result = MagicMock()
        result.scalars.return_value.one.return_value = setting
        session.execute.return_value = result
        repo = SettingRepository(session)

        saved = await repo.set("finance.cycle_start_day", "25")

        assert saved is setting
        session.commit.assert_awaited_once()


class TestListByPrefix:
    async def test_returns_settings_in_key_order(self):
        session = _make_session()
        rows = [Setting(key="travel.checklist.start.a", value="-1"), Setting(key="travel.checklist.start.b", value="-2")]
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        session.execute.return_value = result

        found = await SettingRepository(session).list_by_prefix("travel.checklist.")

        assert found == rows

    async def test_prefix_is_escaped_so_underscores_are_literal(self):
        session = _make_session()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result

        await SettingRepository(session).list_by_prefix("travel_x.")

        sql = str(session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "travel/_x." in sql


class TestDelete:
    async def test_reports_whether_a_row_was_removed(self):
        session = _make_session()
        result = MagicMock()
        result.rowcount = 1
        session.execute.return_value = result

        assert await SettingRepository(session).delete("a.b") is True
        session.commit.assert_awaited()
