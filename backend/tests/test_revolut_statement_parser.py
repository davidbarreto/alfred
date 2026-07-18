from datetime import date
from decimal import Decimal

from app.integrations.revolut.statement_parser import RevolutStatementParser

_CSV_TEXT = """\
Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
Exchange,Current,2025-12-04 01:58:33,2025-12-04 01:58:33,Exchanged to PLN,334.09,0.00,PLN,COMPLETED,334.09
Card Payment,Current,2025-12-04 21:44:13,,Uber,-21.93,0.00,PLN,REVERTED,
Card Payment,Current,2025-12-04 21:59:25,2025-12-05 02:30:37,Bolt,-20.63,0.00,PLN,COMPLETED,313.52
Topup,Current,2025-11-22 22:05:37,2025-11-22 22:05:38,Apple Pay top-up by *1234,1000.00,0.00,EUR,COMPLETED,1000.00
Card Payment,Current,2025-11-22 22:10:04,2025-11-24 15:24:23,Ryanair,-347.94,0.00,EUR,COMPLETED,652.06
Card Refund,Current,2026-04-29 07:40:57,2026-04-30 12:47:18,Some Shop,4.25,0.00,EUR,COMPLETED,656.31
Exchange,Current,2025-12-11 13:36:40,2025-12-11 13:36:40,Exchanged to EUR,-26.78,0.00,PLN,COMPLETED,286.74
Transfer,Current,2026-04-19 23:50:17,2026-04-19 23:50:18,Revolut Bank UAB Sucursal em Portugal,-5.32,0.00,USD,COMPLETED,154.05
Transfer,Current,2026-04-19 02:23:52,2026-04-19 02:23:52,Transfer to SOME PERSON,-32.00,0.00,USD,COMPLETED,28.89
Card Payment,Current,2026-02-27 12:52:27,2026-02-28 05:14:01,Starbucks,-155.00,0.00,CZK,COMPLETED,3536.18
"""


def _content() -> bytes:
    return _CSV_TEXT.encode("utf-8")


class TestCanParse:
    def test_accepts_matching_header(self):
        parser = RevolutStatementParser()
        assert parser.can_parse("revolut.csv", _content()) is True

    def test_rejects_non_csv_extension(self):
        parser = RevolutStatementParser()
        assert parser.can_parse("revolut.pdf", _content()) is False

    def test_rejects_unrelated_csv(self):
        parser = RevolutStatementParser()
        assert parser.can_parse("other.csv", b"col1,col2\n1,2\n") is False

    def test_provider_name(self):
        assert RevolutStatementParser().provider == "revolut"


class TestParse:
    def test_single_pass_produces_all_currencies(self):
        statement = RevolutStatementParser().parse(_content())
        currencies = {r.currency for r in statement.rows}
        assert currencies == {"PLN", "EUR", "USD", "CZK"}

    def test_reverted_rows_are_excluded(self):
        statement = RevolutStatementParser().parse(_content())
        assert all(r.raw_description != "Uber" for r in statement.rows)

    def test_row_count_matches_completed_rows(self):
        statement = RevolutStatementParser().parse(_content())
        # 10 data rows, 1 REVERTED excluded -> 9
        assert len(statement.rows) == 9

    def test_exchange_is_always_a_transfer(self):
        statement = RevolutStatementParser().parse(_content())
        pln_leg = next(r for r in statement.rows if r.raw_description == "Exchanged to PLN")
        eur_leg = next(r for r in statement.rows if r.raw_description == "Exchanged to EUR")
        assert pln_leg.suggested_type == "transfer"
        assert pln_leg.currency == "PLN"
        assert eur_leg.suggested_type == "transfer"
        assert eur_leg.currency == "PLN"  # the outgoing leg is booked on the PLN balance
        assert eur_leg.amount == Decimal("-26.78")

    def test_topup_is_a_transfer_not_income(self):
        statement = RevolutStatementParser().parse(_content())
        topup = next(r for r in statement.rows if "top-up" in r.raw_description)
        assert topup.suggested_type == "transfer"
        assert topup.currency == "EUR"

    def test_card_refund_uses_default_income_inference(self):
        statement = RevolutStatementParser().parse(_content())
        refund = next(r for r in statement.rows if r.raw_description == "Some Shop")
        assert refund.suggested_type is None
        assert refund.amount > 0
        assert refund.currency == "EUR"

    def test_revolut_entity_transfer_is_flagged_uncertain(self):
        statement = RevolutStatementParser().parse(_content())
        internal = next(r for r in statement.rows if "Revolut Bank UAB" in r.raw_description)
        assert internal.suggested_type == "transfer"
        assert internal.flag_reason == "uncertain_transfer"
        assert internal.currency == "USD"

    def test_p2p_transfer_is_left_as_default_expense(self):
        statement = RevolutStatementParser().parse(_content())
        p2p = next(r for r in statement.rows if r.raw_description == "Transfer to SOME PERSON")
        assert p2p.suggested_type is None
        assert p2p.flag_reason is None
        assert p2p.amount < 0

    def test_ordinary_card_payment_untouched(self):
        statement = RevolutStatementParser().parse(_content())
        starbucks = next(r for r in statement.rows if r.raw_description == "Starbucks")
        assert starbucks.suggested_type is None
        assert starbucks.currency == "CZK"

    def test_posted_date_is_completed_date_value_date_is_started_date(self):
        statement = RevolutStatementParser().parse(_content())
        bolt = next(r for r in statement.rows if r.raw_description == "Bolt")
        assert bolt.date_posted == date(2025, 12, 5)
        assert bolt.date_value == date(2025, 12, 4)

    def test_period_spans_all_currencies(self):
        statement = RevolutStatementParser().parse(_content())
        assert statement.period_start == date(2025, 11, 22)
        assert statement.period_end == date(2026, 4, 30)

    def test_empty_file_yields_empty_statement(self):
        statement = RevolutStatementParser().parse(
            b"Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        )
        assert statement.rows == []
        assert statement.period_start is None
