import pytest
from datetime import datetime, date
from freezegun import freeze_time
from unittest.mock import patch

from app.nlp.normalizer import clean_text, normalize_date, normalize_priority
from app.nlp.extractor import extract_entities, extract_finance_entities, extract_time_range

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


# ── extract_finance_entities ──────────────────────────────────────────────────

class TestExtractFinanceEntities:

    # --- Amount and currency ---

    def test_amount_with_dollar_symbol(self):
        _, entities = extract_finance_entities("$50.00 coffee")
        assert entities["amount"] == 50.0
        assert entities["currency"] == "USD"

    def test_amount_with_euro_symbol(self):
        _, entities = extract_finance_entities("€30.50 lunch")
        assert entities["amount"] == 30.5
        assert entities["currency"] == "EUR"

    def test_amount_with_pound_symbol(self):
        _, entities = extract_finance_entities("£12.99 magazine")
        assert entities["amount"] == 12.99
        assert entities["currency"] == "GBP"

    def test_amount_currency_word_euros(self):
        _, entities = extract_finance_entities("spent 25 euros on groceries")
        assert entities["amount"] == 25.0
        assert entities["currency"] == "EUR"

    def test_amount_currency_word_dollars(self):
        _, entities = extract_finance_entities("received 1000 dollars salary")
        assert entities["amount"] == 1000.0
        assert entities["currency"] == "USD"

    def test_amount_comma_decimal_separator(self):
        _, entities = extract_finance_entities("paid €9,99 at store")
        assert entities["amount"] == 9.99

    def test_no_amount_key_absent(self):
        _, entities = extract_finance_entities("coffee at Starbucks")
        assert "amount" not in entities

    # --- Merchant extraction ---

    def test_merchant_from_at_keyword(self):
        _, entities = extract_finance_entities("coffee at Starbucks")
        assert entities["merchant"] == "Starbucks"

    def test_merchant_from_from_keyword(self):
        _, entities = extract_finance_entities("bought lunch from Subway")
        assert entities["merchant"] == "Subway"

    def test_no_merchant_when_absent(self):
        _, entities = extract_finance_entities("spent 50 euros")
        assert "merchant" not in entities

    # --- Transaction type detection ---

    def test_expense_type_from_spent(self):
        _, entities = extract_finance_entities("spent €50")
        assert entities["type"] == "expense"

    def test_expense_type_from_paid(self):
        _, entities = extract_finance_entities("paid 30 at restaurant")
        assert entities["type"] == "expense"

    def test_expense_type_from_bought(self):
        _, entities = extract_finance_entities("bought groceries today")
        assert entities["type"] == "expense"

    def test_expense_type_from_charged(self):
        _, entities = extract_finance_entities("charged to card €100")
        assert entities["type"] == "expense"

    def test_income_type_from_received(self):
        _, entities = extract_finance_entities("received $1000")
        assert entities["type"] == "income"

    def test_income_type_from_salary(self):
        _, entities = extract_finance_entities("salary payment this month")
        assert entities["type"] == "income"

    def test_income_type_from_earned(self):
        _, entities = extract_finance_entities("earned €2000 this month")
        assert entities["type"] == "income"

    def test_income_type_from_refund(self):
        _, entities = extract_finance_entities("refund from Amazon €15")
        assert entities["type"] == "income"

    def test_no_type_when_no_intent_keyword(self):
        _, entities = extract_finance_entities("coffee at Starbucks €4")
        assert "type" not in entities

    # --- Date extraction ---

    @freeze_time(FIXED_NOW)
    def test_date_today_extracted(self):
        _, entities = extract_finance_entities("paid €20 at cafe today", base_date=FIXED_NOW)
        assert entities["date"] == "2024-05-20"

    @freeze_time(FIXED_NOW)
    def test_date_yesterday_extracted(self):
        _, entities = extract_finance_entities("spent €30 yesterday", base_date=FIXED_NOW)
        assert entities["date"] == "2024-05-19"

    def test_no_date_when_absent(self):
        _, entities = extract_finance_entities("spent €50 at Supermarket")
        assert "date" not in entities

    # --- Combined extraction ---

    def test_combined_amount_merchant_type(self):
        _, entities = extract_finance_entities("spent €45.50 at Supermarket")
        assert entities["amount"] == 45.5
        assert entities["currency"] == "EUR"
        assert entities["merchant"] == "Supermarket"
        assert entities["type"] == "expense"

    @freeze_time(FIXED_NOW)
    def test_all_fields_at_once(self):
        _, entities = extract_finance_entities(
            "paid €12.50 at Starbucks today", base_date=FIXED_NOW
        )
        assert entities["amount"] == 12.5
        assert entities["currency"] == "EUR"
        assert entities["merchant"] == "Starbucks"
        assert entities["type"] == "expense"
        assert entities["date"] == "2024-05-20"

    # --- Text passthrough ---

    def test_original_text_returned_unchanged(self):
        text = "spent €50 at Starbucks"
        returned_text, _ = extract_finance_entities(text)
        assert returned_text == text

    def test_empty_string_returns_empty_entities(self):
        text, entities = extract_finance_entities("")
        assert entities == {}
        assert text == ""


# ── extract_time_range ────────────────────────────────────────────────────────

class TestExtractTimeRange:
    def test_24h_range_with_h_suffix(self):
        cleaned, entities = extract_time_range("Test calendar example today from 19h to 21h")
        assert cleaned == "Test calendar example today"
        assert entities == {"start_time": "19:00", "end_time": "21:00"}

    def test_24h_range_with_minutes(self):
        cleaned, entities = extract_time_range("Standup from 9h30 to 10h00")
        assert entities == {"start_time": "09:30", "end_time": "10:00"}
        assert "from" not in cleaned

    def test_colon_range(self):
        cleaned, entities = extract_time_range("Standup from 9:00 to 9:15")
        assert entities == {"start_time": "09:00", "end_time": "09:15"}

    def test_ampm_range(self):
        _, entities = extract_time_range("Party from 7pm to 11pm")
        assert entities == {"start_time": "19:00", "end_time": "23:00"}

    def test_range_with_unmarked_start(self):
        _, entities = extract_time_range("Meeting from 7 to 9pm")
        assert entities == {"start_time": "07:00", "end_time": "21:00"}

    def test_single_time_with_at_and_ampm(self):
        cleaned, entities = extract_time_range("Doctor visit at 9am")
        assert cleaned == "Doctor visit"
        assert entities == {"start_time": "09:00"}

    def test_single_time_bare_24h(self):
        cleaned, entities = extract_time_range("Capoeira class 19h")
        assert cleaned == "Capoeira class"
        assert entities == {"start_time": "19:00"}

    def test_single_time_with_minutes_and_ampm(self):
        _, entities = extract_time_range("Call at 7:30pm")
        assert entities == {"start_time": "19:30"}

    def test_noon_and_midnight_edge_cases(self):
        _, entities = extract_time_range("Lunch at 12pm")
        assert entities == {"start_time": "12:00"}
        _, entities = extract_time_range("Reset at 12am")
        assert entities == {"start_time": "00:00"}

    def test_no_time_returns_empty_entities(self):
        cleaned, entities = extract_time_range("Just a plain title")
        assert cleaned == "Just a plain title"
        assert entities == {}

    def test_invalid_hour_ignored(self):
        # "25h" is not a valid time-of-day, so no start_time should be set
        _, entities = extract_time_range("Weird event at 25h")
        assert "start_time" not in entities
