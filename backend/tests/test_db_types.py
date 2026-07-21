from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.db.types import LocalDateTime


class TestProcessBindParam:
    def test_none_passes_through(self):
        assert LocalDateTime().process_bind_param(None, None) is None

    def test_naive_input_assumed_current_local_zone(self, monkeypatch):
        monkeypatch.setattr("app.db.types.local_timezone", lambda: ZoneInfo("Europe/Lisbon"))

        result = LocalDateTime().process_bind_param(datetime(2026, 8, 1, 15, 0), None)

        assert result == datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)

    def test_aware_input_converted_directly_regardless_of_current_zone(self, monkeypatch):
        monkeypatch.setattr("app.db.types.local_timezone", lambda: ZoneInfo("Europe/Lisbon"))

        result = LocalDateTime().process_bind_param(
            datetime(2026, 8, 1, 15, 0, tzinfo=ZoneInfo("America/New_York")), None
        )

        assert result == datetime(2026, 8, 1, 19, 0, tzinfo=timezone.utc)


class TestProcessResultValue:
    def test_none_passes_through(self):
        assert LocalDateTime().process_result_value(None, None) is None

    def test_converts_utc_to_naive_current_local_zone(self, monkeypatch):
        monkeypatch.setattr("app.db.types.local_timezone", lambda: ZoneInfo("Europe/Lisbon"))

        result = LocalDateTime().process_result_value(
            datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc), None
        )

        assert result == datetime(2026, 8, 1, 15, 0)
        assert result.tzinfo is None

    def test_round_trip_preserves_wall_clock_when_zone_unchanged(self, monkeypatch):
        monkeypatch.setattr("app.db.types.local_timezone", lambda: ZoneInfo("Europe/Lisbon"))
        original = datetime(2026, 8, 1, 15, 0)

        stored = LocalDateTime().process_bind_param(original, None)
        read_back = LocalDateTime().process_result_value(stored, None)

        assert read_back == original

    def test_reprojects_correctly_when_configured_zone_changes_later(self, monkeypatch):
        # This is the scenario the fix targets: a row written while TIMEZONE
        # was Europe/Lisbon must still reproject to the correct equivalent
        # wall-clock time after TIMEZONE is later reconfigured, instead of
        # having its digits silently relabeled under the new zone.
        monkeypatch.setattr("app.db.types.local_timezone", lambda: ZoneInfo("Europe/Lisbon"))
        stored = LocalDateTime().process_bind_param(datetime(2026, 8, 1, 15, 0), None)

        monkeypatch.setattr("app.db.types.local_timezone", lambda: ZoneInfo("America/New_York"))
        read_back = LocalDateTime().process_result_value(stored, None)

        assert read_back == datetime(2026, 8, 1, 10, 0)
