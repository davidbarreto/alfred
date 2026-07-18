from datetime import date
from decimal import Decimal

from app.integrations.coverflex.card_statement_parser import CoverflexCardStatementParser

_CSV_TEXT = """\
id,date,type,status,merchant,amount,currency,is_debit,category,product,voucher_count,voucher_amount,rejection_reason
11111111-0000-0000-0000-000000000001,2026-06-01,transfer,confirmed,COVERFLEX TOPUP ITEMID:ABC123,200.00,EUR,false,,,,,
22222222-0000-0000-0000-000000000002,2026-06-05,purchase,confirmed,SOME CAFE,-8.50,EUR,true,,,,,
33333333-0000-0000-0000-000000000003,2026-06-10,purchase,rejected,SOME RESTAURANT,-15.00,EUR,true,,,,,Insufficient balance
44444444-0000-0000-0000-000000000004,2026-06-12,purchase,confirmed,SOME BAKERY,-3.20,EUR,true,,,,,
"""

_HEADER = (
    "id,date,type,status,merchant,amount,currency,is_debit,category,product,"
    "voucher_count,voucher_amount,rejection_reason"
)


def _content() -> bytes:
    return _CSV_TEXT.encode("utf-8")


class TestCanParse:
    def test_accepts_matching_header(self):
        parser = CoverflexCardStatementParser()
        assert parser.can_parse("coverflex.csv", _content()) is True

    def test_rejects_non_csv_extension(self):
        parser = CoverflexCardStatementParser()
        assert parser.can_parse("coverflex.pdf", _content()) is False

    def test_rejects_unrelated_csv(self):
        parser = CoverflexCardStatementParser()
        assert parser.can_parse("other.csv", b"col1,col2\n1,2\n") is False

    def test_provider_name(self):
        assert CoverflexCardStatementParser().provider == "coverflex_card"


class TestParse:
    def test_metadata(self):
        statement = CoverflexCardStatementParser().parse(_content())
        assert statement.provider == "coverflex_card"
        assert statement.currency == "EUR"
        assert statement.account_number is None
        assert statement.closing_balance is None

    def test_rejected_rows_are_excluded(self):
        statement = CoverflexCardStatementParser().parse(_content())
        assert all(r.raw_description != "SOME RESTAURANT" for r in statement.rows)

    def test_row_count_matches_confirmed_rows(self):
        statement = CoverflexCardStatementParser().parse(_content())
        # 4 data rows, 1 rejected excluded -> 3
        assert len(statement.rows) == 3

    def test_topup_uses_default_income_inference(self):
        statement = CoverflexCardStatementParser().parse(_content())
        topup = next(r for r in statement.rows if "TOPUP" in r.raw_description)
        assert topup.suggested_type is None
        assert topup.amount == Decimal("200.00")

    def test_purchase_uses_default_expense_inference(self):
        statement = CoverflexCardStatementParser().parse(_content())
        purchase = next(r for r in statement.rows if r.raw_description == "SOME CAFE")
        assert purchase.suggested_type is None
        assert purchase.amount == Decimal("-8.50")

    def test_no_running_balance(self):
        statement = CoverflexCardStatementParser().parse(_content())
        assert all(r.balance_after is None for r in statement.rows)

    def test_single_date_used_for_both_dates(self):
        statement = CoverflexCardStatementParser().parse(_content())
        bakery = next(r for r in statement.rows if r.raw_description == "SOME BAKERY")
        assert bakery.date_posted == date(2026, 6, 12)
        assert bakery.date_value == date(2026, 6, 12)

    def test_period_spans_confirmed_rows_only(self):
        statement = CoverflexCardStatementParser().parse(_content())
        assert statement.period_start == date(2026, 6, 1)
        assert statement.period_end == date(2026, 6, 12)

    def test_empty_file_yields_empty_statement(self):
        statement = CoverflexCardStatementParser().parse((_HEADER + "\n").encode("utf-8"))
        assert statement.rows == []
        assert statement.period_start is None
