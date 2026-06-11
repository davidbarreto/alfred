import pytest
from datetime import datetime, date
from freezegun import freeze_time
from unittest.mock import patch

from app.nlp.normalizer import clean_text, normalize_date, normalize_priority
from app.nlp.extractor import extract_entities

FIXED_NOW = datetime(2024, 5, 20)  # Monday


# ── clean_text ────────────────────────────────────────────────────────────────

class TestCleanText:
    def test_remind_me_to(self):
        assert clean_text("remind me to buy milk") == "buy milk"

    def test_please_and_thanks(self):
        assert clean_text("please call the doctor thanks") == "call the doctor"

    def test_i_need_to(self):
        assert clean_text("  i need to   fix the car  ") == "fix the car"

    def test_i_have_to(self):
        assert clean_text("i have to submit the report") == "submit the report"

    def test_i_must(self):
        assert clean_text("i must finish this today") == "finish this today"

    def test_i_should(self):
        assert clean_text("i should call mom") == "call mom"

    def test_dont_forget_to(self):
        assert clean_text("don't forget to take out the trash") == "take out the trash"

    def test_can_you(self):
        assert clean_text("can you book a table") == "book a table"

    def test_could_you(self):
        assert clean_text("could you fix the bug") == "fix the bug"

    def test_remember_to(self):
        assert clean_text("remember to water the plants") == "water the plants"

    def test_make_sure_to(self):
        assert clean_text("make sure to review the PR") == "review the PR"

    def test_no_filler(self):
        assert clean_text("buy groceries") == "buy groceries"

    def test_extra_whitespace_collapsed(self):
        result = clean_text("fix   the   car")
        assert "  " not in result

    def test_empty_string(self):
        assert clean_text("") == ""


# ── normalize_date ────────────────────────────────────────────────────────────

class TestNormalizeDate:
    def test_iso_date_passthrough(self):
        assert normalize_date("2025-12-25") == "2025-12-25"

    def test_empty_returns_none(self):
        assert normalize_date("") is None

    def test_none_input_returns_none(self):
        assert normalize_date(None) is None  # type: ignore[arg-type]

    @freeze_time(FIXED_NOW)
    def test_tomorrow(self):
        assert normalize_date("tomorrow") == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_today(self):
        result = normalize_date("today", base_date=FIXED_NOW)
        assert result == "2024-05-20"

    @freeze_time(FIXED_NOW)
    def test_yesterday(self):
        result = normalize_date("yesterday", base_date=FIXED_NOW)
        assert result == "2024-05-19"

    @freeze_time(FIXED_NOW)
    def test_next_week(self):
        result = normalize_date("next week", base_date=FIXED_NOW)
        assert result is not None
        assert len(result) == 10

    @freeze_time(FIXED_NOW)
    def test_weekday_sunday(self):
        # 2024-05-20 is Monday, next Sunday is 2024-05-26
        result = normalize_date("sunday", base_date=FIXED_NOW)
        assert result == "2024-05-26"

    @freeze_time(FIXED_NOW)
    def test_in_n_days(self):
        result = normalize_date("in 2 days", base_date=FIXED_NOW)
        assert result == "2024-05-22"

    @freeze_time(FIXED_NOW)
    def test_in_n_weeks(self):
        result = normalize_date("in 1 week", base_date=FIXED_NOW)
        assert result == "2024-05-27"

    @freeze_time(FIXED_NOW)
    def test_in_n_months(self):
        result = normalize_date("in 1 month", base_date=FIXED_NOW)
        # dateparser computes 1 calendar month from 2024-05-20 = 2024-06-20
        assert result == "2024-06-20"

    def test_returns_valid_iso_format(self):
        result = normalize_date("tomorrow")
        assert result is not None
        assert len(result) == 10
        year, month, day = result.split("-")
        assert len(year) == 4 and len(month) == 2 and len(day) == 2

    # Test fallback path when dateparser returns None
    @freeze_time(FIXED_NOW)
    def test_fallback_today(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("today", base_date=FIXED_NOW)
            assert result == "2024-05-20"

    @freeze_time(FIXED_NOW)
    def test_fallback_tomorrow(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("tomorrow", base_date=FIXED_NOW)
            assert result == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_fallback_yesterday(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("yesterday", base_date=FIXED_NOW)
            assert result == "2024-05-19"

    @freeze_time(FIXED_NOW)
    def test_fallback_iso(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("2025-01-15", base_date=FIXED_NOW)
            assert result == "2025-01-15"

    @freeze_time(FIXED_NOW)
    def test_fallback_next_monday(self):
        # 2024-05-20 is Monday, next Monday is 2024-05-27
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("next monday", base_date=FIXED_NOW)
            assert result == "2024-05-27"

    @freeze_time(FIXED_NOW)
    def test_fallback_this_friday(self):
        # 2024-05-20 is Monday, this Friday is 2024-05-24
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("this friday", base_date=FIXED_NOW)
            assert result == "2024-05-24"

    @freeze_time(FIXED_NOW)
    def test_fallback_weekday(self):
        # friday from Monday 2024-05-20 → 2024-05-24
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("friday", base_date=FIXED_NOW)
            assert result == "2024-05-24"

    @freeze_time(FIXED_NOW)
    def test_fallback_in_days(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("in 3 days", base_date=FIXED_NOW)
            assert result == "2024-05-23"

    @freeze_time(FIXED_NOW)
    def test_fallback_in_weeks(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("in 2 weeks", base_date=FIXED_NOW)
            assert result == "2024-06-03"

    @freeze_time(FIXED_NOW)
    def test_fallback_in_months(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("in 2 months", base_date=FIXED_NOW)
            assert result == "2024-07-19"

    def test_fallback_no_match_returns_none(self):
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("not-a-real-date-string-xyz")
            assert result is None

    @freeze_time(FIXED_NOW)
    def test_base_date_as_date_object(self):
        base = FIXED_NOW.date()
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("today", base_date=base)
            assert result == "2024-05-20"

    @freeze_time(FIXED_NOW)
    def test_fallback_weekday_already_past(self):
        # If today is Monday (0), asking for monday again should give next monday (7 days ahead)
        with patch("app.nlp.normalizer.dateparser.parse", return_value=None):
            result = normalize_date("monday", base_date=FIXED_NOW)
            assert result == "2024-05-27"


# ── normalize_priority ────────────────────────────────────────────────────────

class TestNormalizePriority:
    @pytest.mark.parametrize("raw,expected", [
        ("urgent", "HIGH"),
        ("urgently", "HIGH"),
        ("asap", "HIGH"),
        ("as soon as possible", "HIGH"),
        ("critical", "HIGH"),
        ("important", "MEDIUM"),
        ("low priority", "LOW"),
        ("not urgent", "LOW"),
        ("URGENT", "HIGH"),   # case insensitive
        ("CRITICAL", "HIGH"),
    ])
    def test_known_keywords(self, raw, expected):
        assert normalize_priority(raw) == expected

    def test_unknown_keyword_passthrough(self):
        assert normalize_priority("somerandompriority") == "somerandompriority"

    def test_already_canonical(self):
        assert normalize_priority("HIGH") == "HIGH"


# ── extract_entities ──────────────────────────────────────────────────────────

class TestExtractEntities:
    def test_priority_urgent(self):
        cleaned, entities = extract_entities("buy milk urgently")
        assert entities["priority"] == "HIGH"
        assert "urgently" not in cleaned

    @freeze_time(FIXED_NOW)
    def test_date_next_monday(self):
        cleaned, entities = extract_entities("call mom next monday", base_date=FIXED_NOW)
        assert "deadline" in entities
        assert "next monday" not in cleaned

    @freeze_time(FIXED_NOW)
    def test_both_priority_and_date(self):
        cleaned, entities = extract_entities(
            "remind me to finish the report asap by friday", base_date=FIXED_NOW
        )
        assert entities["priority"] == "HIGH"
        assert "deadline" in entities
        assert "asap" not in cleaned

    def test_no_matches_returns_cleaned_text(self):
        cleaned, entities = extract_entities("buy groceries")
        assert cleaned == "buy groceries"
        assert entities == {}

    def test_multiple_priorities_high_wins(self):
        cleaned, entities = extract_entities("important task that is also critical")
        assert entities["priority"] == "HIGH"

    def test_only_low_priority(self):
        cleaned, entities = extract_entities("low priority task for later")
        assert entities["priority"] == "LOW"

    @freeze_time(FIXED_NOW)
    def test_date_today(self):
        cleaned, entities = extract_entities("submit report today", base_date=FIXED_NOW)
        assert entities["deadline"] == "2024-05-20"
        assert "today" not in cleaned

    @freeze_time(FIXED_NOW)
    def test_date_tomorrow(self):
        cleaned, entities = extract_entities("call dentist tomorrow", base_date=FIXED_NOW)
        assert entities["deadline"] == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_date_iso(self):
        cleaned, entities = extract_entities("meeting on 2024-06-01", base_date=FIXED_NOW)
        assert entities["deadline"] == "2024-06-01"

    def test_no_base_date_uses_now(self):
        cleaned, entities = extract_entities("do it tomorrow")
        assert "deadline" in entities

    @freeze_time(FIXED_NOW)
    def test_date_normalize_fails_no_deadline(self):
        # If the matched date string can't be normalized, no deadline is set
        # but the text is still cleaned
        with patch("app.nlp.extractor.normalize_date", return_value=None):
            cleaned, entities = extract_entities("do it tomorrow", base_date=FIXED_NOW)
            assert "deadline" not in entities
