import pytest

from app.config import DEFAULT_HOLIDAY_CALENDARS, Settings, parse_holiday_calendars


class TestParseHolidayCalendars:
    def test_parses_pairs_keeping_the_hash_and_at_of_calendar_ids(self):
        parsed = parse_holiday_calendars("PT=pt.portuguese#holiday@group.v.calendar.google.com, UK = uk-cal ,")

        assert parsed == {"PT": "pt.portuguese#holiday@group.v.calendar.google.com", "UK": "uk-cal"}

    @pytest.mark.parametrize("raw", ["PT", "=cal", "PT="])
    def test_rejects_malformed_entries(self, raw):
        with pytest.raises(ValueError, match="CODE=calendar_id"):
            parse_holiday_calendars(raw)


class TestSettingsHolidayCalendars:
    def test_default_is_portugal_and_brazil(self, monkeypatch):
        monkeypatch.delenv("HOLIDAY_CALENDARS", raising=False)

        assert set(Settings().holiday_calendar_map) == {"PT", "BR"}

    def test_empty_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("HOLIDAY_CALENDARS", "")

        assert Settings().holiday_calendars == DEFAULT_HOLIDAY_CALENDARS

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv("HOLIDAY_CALENDARS", "UK=uk-cal")

        assert Settings().holiday_calendar_map == {"UK": "uk-cal"}
