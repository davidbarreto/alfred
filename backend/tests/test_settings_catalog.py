from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.core.settings.catalog import NAMESPACES, build_catalog, catalog_fields
from app.features.core.settings.catalog_service import SettingsCatalogService

AUTH = {"Authorization": "Bearer test-api-token"}


def _fields(catalog):
    return {f.key: f for ns in catalog.namespaces for f in ns.fields}


class TestCoverage:
    def test_every_settings_field_has_a_title(self):
        untitled = [f"{source.schema.__name__}.{name}" for _, source, name, info in catalog_fields() if not info.title]
        assert untitled == []

    def test_every_field_of_every_schema_is_in_the_catalog(self):
        catalog = _fields(build_catalog())
        for namespace in NAMESPACES:
            for source in namespace.sources:
                expected = set(source.schema.model_fields) - source.exclude
                listed = {f.field for f in catalog.values() if f.read_path == source.read_path}
                assert listed == expected, source.schema.__name__

    def test_keys_are_unique(self):
        fields = [f.key for ns in build_catalog().namespaces for f in ns.fields]
        assert len(fields) == len(set(fields))

    def test_planning_never_offers_travel_times(self):
        assert "planning.travel_times" not in _fields(build_catalog())


class TestFieldShape:
    def test_number_carries_limits_unit_group_and_default(self):
        field = _fields(build_catalog())["travel.airport_buffer_min"]
        assert (field.widget, field.type, field.min, field.max) == ("number", "integer", 0, 600)
        assert (field.unit, field.group) == ("min", "Getting to the airport")
        assert (field.has_default, field.default) == (True, 120)
        assert field.nullable is False
        assert field.write_path == field.read_path == "/travel/settings"

    def test_optional_field_without_default_is_nullable(self):
        field = _fields(build_catalog())["planning.wake_time"]
        assert (field.widget, field.nullable, field.has_default, field.default) == ("time", True, False, None)

    def test_widget_from_type_when_no_hint(self):
        fields = _fields(build_catalog())
        assert fields["travel.snooze_other_events"].widget == "toggle"
        assert fields["planning.work_tag"].widget == "text"

    def test_max_length_is_listed(self):
        field = _fields(build_catalog())["planning.conventions"]
        assert field.widget == "longtext"
        assert field.max_length is not None

    def test_home_city_has_a_confirm_note(self):
        assert "already started" in _fields(build_catalog())["travel.home_city_id"].confirm_note

    def test_cascades_are_json_written_per_entry(self):
        field = _fields(build_catalog())["organizer.calendar_notification_cascades"]
        assert (field.widget, field.type, field.field) == ("json", "object", "profiles")
        assert field.options == ["cant_miss", "important", "normal", "light", "aware"]
        assert field.write_path == "/organizer/calendar-notification-settings/{entry}"
        assert field.entry_field == "offsets"
        assert field.default["normal"] == ["1h", "10m", "0"]

    def test_birthday_cascades_key(self):
        field = _fields(build_catalog())["organizer.contact_birthday_cascades"]
        assert field.options == ["family", "relative", "friend", "other"]

    def test_env_backed_defaults_come_from_env(self):
        fields = _fields(build_catalog())
        assert fields["reminders.urgency_reset_days"].default == 7
        assert fields["reminders.undated_task_snooze_days"].default == 7

    def test_persona_additions_is_markdown_next_to_the_base_persona(self):
        field = _fields(build_catalog())["assistant.persona_additions"]
        assert (field.widget, field.reference, field.max_length) == ("markdown", "base_persona", 20000)
        assert field.reference_label.startswith("Base persona")

    def test_checklist_template_is_a_list_written_whole(self):
        field = _fields(build_catalog())["travel.checklist"]
        assert (field.widget, field.type, field.field, field.has_default) == ("checklist", "array", "items", False)
        assert field.read_path == field.write_path == "/travel/checklist-template"


class TestService:
    async def test_returns_the_catalog(self):
        catalog = await SettingsCatalogService().get()
        assert "travel.checklist" in _fields(catalog)


class TestRoute:
    @pytest.fixture
    def client(self):
        from app.dependencies import get_settings_catalog_service
        from app.main import app

        service = AsyncMock()
        service.get.return_value = build_catalog()
        app.dependency_overrides[get_settings_catalog_service] = lambda: service
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_returns_the_catalog(self, client):
        response = client.get("/core/settings/catalog", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert [ns["namespace"] for ns in body["namespaces"]] == [
            "planning", "reminders", "travel", "briefing", "finance", "study", "cs", "metrics", "language", "organizer",
            "weather", "chat", "assistant",
        ]
        assert set(body) == {"namespaces"}

    def test_requires_auth(self, client):
        assert client.get("/core/settings/catalog").status_code == 403
