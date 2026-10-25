import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.features.planning.schemas import PlanningSettingsUpdate
from app.features.planning.settings_service import (
    DEFAULT_OFFICE_TAG,
    DEFAULT_WORK_TAG,
    DEFAULT_WORK_TARGET_MINUTES,
    PlanningSettingsService,
)


class _FakeStore:
    def __init__(self, values=None):
        self.values = dict(values or {})

    async def get_value(self, key, default=None):
        return self.values.get(key, default)

    async def set_value(self, key, value):
        self.values[key] = value


@pytest.fixture
def store():
    return _FakeStore()


@pytest.fixture
def service(store):
    svc = PlanningSettingsService(session=AsyncMock())
    svc._settings = store
    return svc


class TestRead:
    async def test_defaults_are_generic_and_nothing_personal_is_seeded(self, service):
        settings = await service.get()
        assert settings.work_target_minutes == DEFAULT_WORK_TARGET_MINUTES == 480
        assert (settings.work_tag, settings.office_tag) == (DEFAULT_WORK_TAG, DEFAULT_OFFICE_TAG) == ("work", "office")
        assert settings.wake_time is None and settings.sleep_time is None
        assert settings.preferred_work_windows == []
        assert settings.office_days_per_week is None and settings.office_min_minutes is None

    async def test_reads_stored_values(self, service, store):
        store.values.update({
            "planning.wake_time": "07:30", "planning.work_target_minutes": "420",
            "planning.preferred_work_windows": json.dumps(["10:00-14:00"]),
            "planning.office_days_per_week": "4", "planning.office_min_minutes": "0",
        })
        settings = await service.get()
        assert (settings.wake_time, settings.work_target_minutes) == ("07:30", 420)
        assert settings.preferred_work_windows == ["10:00-14:00"]
        assert (settings.office_days_per_week, settings.office_min_minutes) == (4, 0)


class TestUpdate:
    async def test_stores_under_the_planning_prefix(self, service, store):
        result = await service.update(PlanningSettingsUpdate(
            wake_time="07:30", work_target_minutes=420, preferred_work_windows=["10:00-14:00", "16:00-18:00"],
            office_days_per_week=3, work_tag="job",
        ))
        assert store.values["planning.wake_time"] == "07:30"
        assert json.loads(store.values["planning.preferred_work_windows"]) == ["10:00-14:00", "16:00-18:00"]
        assert (result.work_target_minutes, result.work_tag, result.office_days_per_week) == (420, "job", 3)

    async def test_untouched_fields_are_left_alone(self, service, store):
        store.values["planning.wake_time"] = "07:30"
        await service.update(PlanningSettingsUpdate(sleep_time="23:30"))
        assert store.values["planning.wake_time"] == "07:30"

    async def test_explicit_null_resets_to_default(self, service, store):
        store.values.update({"planning.office_days_per_week": "4", "planning.work_target_minutes": "420"})
        result = await service.update(PlanningSettingsUpdate(office_days_per_week=None, work_target_minutes=None))
        assert result.office_days_per_week is None
        assert result.work_target_minutes == DEFAULT_WORK_TARGET_MINUTES

    async def test_empty_window_list_clears_the_setting(self, service, store):
        store.values["planning.preferred_work_windows"] = json.dumps(["10:00-14:00"])
        result = await service.update(PlanningSettingsUpdate(preferred_work_windows=[]))
        assert result.preferred_work_windows == []


class TestValidation:
    @pytest.mark.parametrize("field,value", [
        ("wake_time", "7:30"), ("sleep_time", "25:00"), ("work_target_minutes", -1), ("work_target_minutes", 2000),
        ("office_days_per_week", 0), ("office_days_per_week", 8), ("office_min_minutes", -5),
        ("work_tag", "  "), ("preferred_work_windows", ["14:00-10:00"]), ("preferred_work_windows", ["morning"]),
        ("preferred_work_windows", ["10:00-10:00"]),
    ])
    def test_invalid_values_rejected(self, field, value):
        with pytest.raises(ValidationError):
            PlanningSettingsUpdate(**{field: value})

    def test_tags_are_trimmed(self):
        assert PlanningSettingsUpdate(work_tag=" job ").work_tag == "job"
