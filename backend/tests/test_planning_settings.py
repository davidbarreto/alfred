import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.features.planning.schemas import PlanningSettingsUpdate, parse_travel_times
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


class TestWorkdays:
    async def test_default_is_monday_to_friday(self, service):
        assert (await service.get()).workdays == ["mon", "tue", "wed", "thu", "fri"]

    async def test_update_stores_sorted_lowercase_and_empty_resets(self, service, store):
        result = await service.update(PlanningSettingsUpdate(workdays=["Sat", "mon"]))
        assert json.loads(store.values["planning.workdays"]) == ["mon", "sat"]
        assert result.workdays == ["mon", "sat"]

        reset = await service.update(PlanningSettingsUpdate(workdays=[]))
        assert reset.workdays == ["mon", "tue", "wed", "thu", "fri"]

    def test_unknown_day_is_rejected(self):
        with pytest.raises(ValidationError):
            PlanningSettingsUpdate(workdays=["funday"])


class TestConventions:
    async def test_unset_by_default(self, service):
        assert (await service.get()).conventions is None

    async def test_stored_trimmed_and_read_back(self, service, store):
        result = await service.update(PlanningSettingsUpdate(conventions="  Home by 14:00.\nOnly meds after 22:00.  "))
        assert store.values["planning.conventions"] == "Home by 14:00.\nOnly meds after 22:00."
        assert result.conventions == "Home by 14:00.\nOnly meds after 22:00."

    async def test_blank_or_null_resets(self, service, store):
        store.values["planning.conventions"] = "x"
        assert (await service.update(PlanningSettingsUpdate(conventions="   "))).conventions is None
        store.values["planning.conventions"] = "x"
        assert (await service.update(PlanningSettingsUpdate(conventions=None))).conventions is None

    def test_length_is_capped(self):
        with pytest.raises(ValidationError):
            PlanningSettingsUpdate(conventions="x" * 2001)


class TestTravelTimes:
    async def test_empty_by_default(self, service):
        assert (await service.get()).travel_times == []

    async def test_stored_as_json_and_read_back(self, service, store):
        result = await service.update(PlanningSettingsUpdate(travel_times=[
            {"place": " Office ", "mode": "Metro", "minutes": 50}, {"place": "office", "mode": "car", "minutes": 20},
        ]))
        assert json.loads(store.values["planning.travel_times"]) == [
            {"place": "office", "mode": "metro", "minutes": 50}, {"place": "office", "mode": "car", "minutes": 20},
        ]
        assert [(t.place, t.mode, t.minutes) for t in result.travel_times] == [("office", "metro", 50), ("office", "car", 20)]

    async def test_empty_list_or_null_resets(self, service, store):
        store.values["planning.travel_times"] = json.dumps([{"place": "office", "mode": "car", "minutes": 20}])
        assert (await service.update(PlanningSettingsUpdate(travel_times=[]))).travel_times == []
        store.values["planning.travel_times"] = json.dumps([{"place": "office", "mode": "car", "minutes": 20}])
        assert (await service.update(PlanningSettingsUpdate(travel_times=None))).travel_times == []

    @pytest.mark.parametrize("entry", [
        {"place": "", "mode": "car", "minutes": 20}, {"place": "office", "mode": "  ", "minutes": 20},
        {"place": "office", "mode": "car", "minutes": 0}, {"place": "office", "mode": "car", "minutes": 601},
    ])
    def test_invalid_entries_rejected(self, entry):
        with pytest.raises(ValidationError):
            PlanningSettingsUpdate(travel_times=[entry])

    def test_a_place_and_mode_pair_can_only_be_listed_once(self):
        entry = {"place": "office", "mode": "car", "minutes": 20}
        with pytest.raises(ValidationError, match="listed twice"):
            PlanningSettingsUpdate(travel_times=[entry, {**entry, "place": "Office", "minutes": 25}])

    def test_the_list_is_capped(self):
        with pytest.raises(ValidationError):
            PlanningSettingsUpdate(travel_times=[{"place": f"p{i}", "mode": "car", "minutes": 5} for i in range(21)])


class TestParseTravelTimes:
    def test_places_separated_by_semicolons_and_modes_by_commas(self):
        assert parse_travel_times("office:metro=50,car=20; school:walk=10") == [
            {"place": "office", "mode": "metro", "minutes": 50},
            {"place": "office", "mode": "car", "minutes": 20},
            {"place": "school", "mode": "walk", "minutes": 10},
        ]

    def test_empty_text_is_an_empty_list(self):
        assert parse_travel_times("  ") == []

    @pytest.mark.parametrize("text", ["office", "office:", "office:metro", "office:metro=fifty", "office:metro=-5", "office:metro=5.5"])
    def test_malformed_text_is_rejected(self, text):
        with pytest.raises(ValueError):
            parse_travel_times(text)
