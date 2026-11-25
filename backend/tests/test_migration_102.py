import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


def _statements(monkeypatch, direction: str) -> list[str]:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "102_home_city_from_home_place.py"
    spec = importlib.util.spec_from_file_location("migration_102", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = []
    monkeypatch.setattr(module.op, "execute", statements.append, raising=False)
    getattr(module, direction)()
    return statements


class TestMigration102:
    def test_upgrade_moves_home_into_the_setting_city_then_deletes_the_setting(self, monkeypatch):
        update, delete = _statements(monkeypatch, "upgrade")
        assert update.startswith("UPDATE location.places p SET city_id = c.id")
        # Only a setting that names an existing city, only the Home place, only when it differs.
        assert "s.value ~ '^[0-9]+$' AND c.id = s.value::int" in update
        assert "s.key = 'travel.home_city_id' AND p.kind = 'home' AND p.city_id <> c.id" in update
        assert delete == "DELETE FROM core.settings WHERE key = 'travel.home_city_id'"

    def test_downgrade_writes_the_setting_back_from_home(self, monkeypatch):
        (insert,) = _statements(monkeypatch, "downgrade")
        assert "SELECT 'travel.home_city_id', city_id::text FROM location.places WHERE kind = 'home'" in insert
        assert "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value" in insert

    @pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
    def test_statements_compile_for_postgres(self, monkeypatch, direction):
        for statement in _statements(monkeypatch, direction):
            # No bind parameters: a stray colon would make text() expect one.
            assert not text(statement).compile(dialect=postgresql.dialect()).params
