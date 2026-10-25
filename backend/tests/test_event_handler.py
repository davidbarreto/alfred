from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from app.assistant.commands.handlers.event import handle_event
from app.features.organizer.calendar_events.schemas import EventFilters, EventRead


def _event_read(**kwargs) -> EventRead:
    defaults = dict(
        id=1,
        title="Team Sync",
        start_datetime=datetime(2026, 10, 21, 10, 0),
        end_datetime=datetime(2026, 10, 21, 11, 0),
        timezone="America/New_York",
    )
    defaults.update(kwargs)
    return EventRead(**defaults)


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.get_events.return_value = [_event_read()]
    return svc


def _filters(service) -> EventFilters:
    return service.get_events.await_args.args[0]


class TestEventListRange:
    # 2026-10-21 12:00 UTC is 13:00 in Lisbon (WEST, UTC+1)
    @freeze_time("2026-10-21 12:00:00")
    async def test_defaults_to_next_14_days(self, service):
        await handle_event("list", {}, service)
        filters = _filters(service)
        assert filters.start_from == datetime(2026, 10, 21, 13, 0)
        assert filters.start_to == datetime(2026, 11, 4, 13, 0)

    async def test_start_and_end_map_to_filter_range(self, service):
        await handle_event(
            "list", {"start": "2026-10-21T00:00:00", "end": "2026-10-21T23:59:59"}, service
        )
        filters = _filters(service)
        assert filters.start_from == datetime(2026, 10, 21, 0, 0)
        assert filters.start_to == datetime(2026, 10, 21, 23, 59, 59)

    async def test_date_only_end_means_end_of_that_day(self, service):
        await handle_event("list", {"start": "2026-10-21", "end": "2026-10-21"}, service)
        filters = _filters(service)
        assert filters.start_from == datetime(2026, 10, 21, 0, 0)
        assert filters.start_to == datetime(2026, 10, 21, 23, 59, 59)

    async def test_start_without_end_spans_14_days(self, service):
        await handle_event("list", {"start": "2026-10-21T08:00:00"}, service)
        filters = _filters(service)
        assert filters.start_to == datetime(2026, 11, 4, 8, 0)

    async def test_offset_inputs_are_converted_to_local_time(self, service):
        await handle_event(
            "list", {"start": "2026-10-21T09:00:00+00:00", "end": "2026-10-21T20:00:00+00:00"}, service
        )
        filters = _filters(service)
        assert filters.start_from == datetime(2026, 10, 21, 10, 0)
        assert filters.start_to == datetime(2026, 10, 21, 21, 0)

    async def test_legacy_date_range_argument_still_works(self, service):
        await handle_event(
            "list",
            {"date_range": {"start": "2026-10-21T00:00:00", "end": "2026-10-22T00:00:00"}},
            service,
        )
        filters = _filters(service)
        assert filters.start_from == datetime(2026, 10, 21, 0, 0)
        assert filters.start_to == datetime(2026, 10, 22, 0, 0)


class TestEventListOutput:
    async def test_result_states_display_timezone(self, service):
        result = await handle_event("list", {}, service)
        assert result["timezone"] == "Europe/Lisbon"
        assert len(result["events"]) == 1

    async def test_events_carry_offsets_and_omit_per_event_timezone(self, service):
        result = await handle_event("list", {}, service)
        event = result["events"][0]
        assert event["start_datetime"] == "2026-10-21T10:00:00+01:00"
        assert event["end_datetime"] == "2026-10-21T11:00:00+01:00"
        assert "timezone" not in event

    async def test_events_include_notification_profile_and_tags(self, service):
        service.get_events.return_value = [_event_read(notification_profile="light", tags=["work"])]
        result = await handle_event("list", {}, service)
        event = result["events"][0]
        assert event["notification_profile"] == "light"
        assert event["tags"] == ["work"]


class TestEventReadSerialization:
    def test_offsets_follow_dst(self):
        summer = _event_read(start_datetime=datetime(2026, 10, 24, 10, 0), end_datetime=datetime(2026, 10, 24, 11, 0))
        winter = _event_read(start_datetime=datetime(2026, 10, 26, 10, 0), end_datetime=datetime(2026, 10, 26, 11, 0))
        assert summer.model_dump(mode="json")["start_datetime"].endswith("+01:00")
        assert winter.model_dump(mode="json")["start_datetime"].endswith("+00:00")


class TestEventFiltersOffsets:
    def test_aware_bounds_are_converted_to_local_naive(self):
        from datetime import timezone

        filters = EventFilters(start_from=datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc))
        assert filters.start_from == datetime(2026, 10, 21, 10, 0)


class TestEventListCatalog:
    def test_list_action_documents_range_and_timezone(self):
        from app.assistant.commands.registry import COMMAND_DEFINITIONS

        config = COMMAND_DEFINITIONS["event"]["list"]
        assert set(config["flags"].values()) == {"start", "end", "limit"}
        assert "14 days" in config["description"]
        assert "timezone" in config["details"]
        assert "notification_profile" in config["details"]
