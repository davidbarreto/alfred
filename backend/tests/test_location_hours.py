from datetime import date, time

import pytest

from app.features.organizer.locations.hours import (
    DayHours,
    HoursError,
    format_hours,
    format_ranges,
    hours_on,
    normalize_hours,
    open_at,
    parse_hours,
)

_WEEKDAYS = {d: [["08:00", "20:00"]] for d in ("mon", "tue", "wed", "thu", "fri")}
_MONDAY = date(2026, 11, 23)
_SUNDAY = date(2026, 11, 29)


class TestParseHours:
    def test_weekday_range_saturday_lunch_break_sunday_closed_and_holidays(self):
        hours = parse_hours("mon-fri 08:00-20:00; sat 9-13, 15:00-19:00; sun closed; holidays closed")

        assert hours == {
            **_WEEKDAYS, "sat": [["09:00", "13:00"], ["15:00", "19:00"]], "sun": [], "hol": [],
        }

    def test_holiday_hours(self):
        assert parse_hours("holidays 09:00-13:00") == {"hol": [["09:00", "13:00"]]}

    def test_daily_full_names_lists_and_spaced_ranges(self):
        assert parse_hours("daily 7-22") == {d: [["07:00", "22:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        assert parse_hours("Monday, Wednesday 9:30-17:00") == {"mon": [["09:30", "17:00"]], "wed": [["09:30", "17:00"]]}
        assert parse_hours("mon - wed 10-18") == {d: [["10:00", "18:00"]] for d in ("mon", "tue", "wed")}

    def test_wrapping_day_range_and_new_lines(self):
        assert parse_hours("fri-mon 10-14\ntue closed") == {
            "fri": [["10:00", "14:00"]], "sat": [["10:00", "14:00"]], "sun": [["10:00", "14:00"]],
            "mon": [["10:00", "14:00"]], "tue": [],
        }

    def test_ranges_are_sorted_and_midnight_end_allowed(self):
        assert parse_hours("sat 15-24, 08-12") == {"sat": [["08:00", "12:00"], ["15:00", "24:00"]]}

    def test_en_dash_is_accepted(self):
        assert parse_hours("mon–fri 08:00–20:00") == _WEEKDAYS

    def test_blank_is_unknown(self):
        assert parse_hours("") is None
        assert parse_hours("  ") is None
        assert parse_hours(None) is None

    @pytest.mark.parametrize("text, message", [
        ("mon", "needs days then hours"),
        ("funday 9-17", r"'funday' is not a day \(use mon, tue, ... sun, daily or holidays\)"),
        ("mon 9-17; mon closed", "more than once"),
        ("mon-fri 9-17; wed closed", "more than once"),
        ("mon 17-9", "must end after it starts"),
        ("mon 9-13, 12-18", "overlap"),
        ("mon 25:00-26:00", "not a time of day"),
        ("mon 9:75-10", "not a time of day"),
        ("mon 9", "is not a range"),
        ("mon 9-17 closed", "is not a range"),
    ])
    def test_bad_input_says_what_is_wrong(self, text, message):
        with pytest.raises(HoursError, match=message):
            parse_hours(text)


class TestFormatHours:
    def test_groups_runs_and_lists_holidays_last(self):
        hours = {**_WEEKDAYS, "sat": [["09:00", "13:00"]], "sun": [], "hol": []}

        assert format_hours(hours) == "mon-fri 08:00-20:00; sat 09:00-13:00; sun closed; holidays closed"

    def test_same_hours_on_separate_days_share_a_segment(self):
        hours = {"mon": [["09:00", "17:00"]], "tue": [], "wed": [["09:00", "17:00"]], "fri": [["09:00", "17:00"]]}

        assert format_hours(hours) == "mon,wed,fri 09:00-17:00; tue closed"

    def test_every_day_alike_is_daily(self):
        assert format_hours(parse_hours("mon-sun 07:00-22:00")) == "daily 07:00-22:00"

    def test_unknown_is_empty(self):
        assert format_hours(None) == ""
        assert format_hours({}) == ""

    @pytest.mark.parametrize("text", [
        "mon-fri 08:00-20:00; sat 09:00-13:00, 15:00-19:00; sun closed; holidays closed",
        "mon,thu 10:00-12:00; holidays 09:00-13:00",
        "daily 00:00-24:00",
    ])
    def test_round_trip_text_json_text(self, text):
        hours = parse_hours(text)

        assert format_hours(hours) == text
        assert parse_hours(format_hours(hours)) == hours

    def test_format_ranges(self):
        assert format_ranges(None) is None
        assert format_ranges([]) == "closed"
        assert format_ranges([["08:00", "13:00"], ["14:00", "19:00"]]) == "08:00-13:00, 14:00-19:00"


class TestNormalizeHours:
    def test_text_is_parsed(self):
        assert normalize_hours("sun closed") == {"sun": []}

    def test_dict_is_cleaned_and_ordered(self):
        assert normalize_hours({"hol": [], "mon": [["9:00", "17:00"]]}) == {"mon": [["09:00", "17:00"]], "hol": []}

    def test_empty_dict_is_unknown(self):
        assert normalize_hours({}) is None

    @pytest.mark.parametrize("value, message", [
        ({"moon": []}, "is not a day"),
        ({"mon": "9-17"}, "list of"),
        ({"mon": [["09:00"]]}, "list of"),
        ({"mon": [["17:00", "09:00"]]}, "must end after"),
        (42, "text or an object"),
    ])
    def test_bad_dict(self, value, message):
        with pytest.raises(HoursError, match=message):
            normalize_hours(value)


class TestHoursOn:
    def test_weekday_hours(self):
        assert hours_on(_WEEKDAYS, _MONDAY, holiday=False) == DayHours([["08:00", "20:00"]])

    def test_missing_day_is_unknown(self):
        assert hours_on(_WEEKDAYS, _SUNDAY, holiday=False) == DayHours(None)
        assert hours_on(None, _SUNDAY, holiday=False) == DayHours(None)

    def test_holiday_uses_holiday_hours(self):
        hours = {**_WEEKDAYS, "hol": []}

        assert hours_on(hours, _MONDAY, holiday=True) == DayHours([], holiday=True)

    def test_holiday_without_holiday_hours_falls_back_to_the_weekday(self):
        assert hours_on(_WEEKDAYS, _MONDAY, holiday=True) == DayHours(
            [["08:00", "20:00"]], holiday=True, holiday_hours_known=False
        )


class TestOpenAt:
    def test_inside_and_outside_ranges(self):
        ranges = [["08:00", "13:00"], ["14:00", "19:00"]]

        assert open_at(ranges, time(8, 0)) is True
        assert open_at(ranges, time(13, 30)) is False
        assert open_at(ranges, time(19, 0)) is False

    def test_closed_and_unknown(self):
        assert open_at([], time(12)) is False
        assert open_at(None, time(12)) is None

    def test_until_midnight(self):
        assert open_at([["20:00", "24:00"]], time(23, 59)) is True
