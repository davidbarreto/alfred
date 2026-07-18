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
    def test_accepts_matching_currency(self):
        parser = RevolutStatementParser("EUR")
        assert parser.can_parse("revolut.csv", _content()) is True

    def test_rejects_currency_absent_from_file(self):
        parser = RevolutStatementParser("GBP")
        assert parser.can_parse("revolut.csv", _content()) is False

    def test_rejects_non_csv_extension(self):
        parser = RevolutStatementParser("EUR")
        assert parser.can_parse("revolut.pdf", _content()) is False

    def test_rejects_unrelated_csv(self):
        parser = RevolutStatementParser("EUR")
        assert parser.can_parse("other.csv", b"col1,col2\n1,2\n") is False

    def test_provider_name_is_currency_scoped(self):
        assert RevolutStatementParser("EUR").provider == "revolut_eur"
        assert RevolutStatementParser("pln").provider == "revolut_pln"


class TestParse:
    def test_filters_to_own_currency_only(self):
        statement = RevolutStatementParser("EUR").parse(_content())
        assert statement.currency == "EUR"
        assert all(r.raw_description not in ("Bolt", "Starbucks") for r in statement.rows)

    def test_reverted_rows_are_excluded(self):
        statement = RevolutStatementParser("PLN").parse(_content())
        assert all(r.raw_description != "Uber" for r in statement.rows)

    def test_exchange_is_always_a_transfer(self):
        pln = RevolutStatementParser("PLN").parse(_content())
        by_desc = {r.raw_description: r for r in pln.rows}
        assert by_desc["Exchanged to PLN"].suggested_type == "transfer"
        assert by_desc["Exchanged to EUR"].suggested_type == "transfer"
        assert by_desc["Exchanged to EUR"].amount == Decimal("-26.78")

    def test_topup_is_a_transfer_not_income(self):
        eur = RevolutStatementParser("EUR").parse(_content())
        topup = next(r for r in eur.rows if "top-up" in r.raw_description)
        assert topup.suggested_type == "transfer"

    def test_card_refund_uses_default_income_inference(self):
        eur = RevolutStatementParser("EUR").parse(_content())
        refund = next(r for r in eur.rows if r.raw_description == "Some Shop")
        assert refund.suggested_type is None
        assert refund.amount > 0

    def test_revolut_entity_transfer_is_flagged_uncertain(self):
        usd = RevolutStatementParser("USD").parse(_content())
        internal = next(r for r in usd.rows if "Revolut Bank UAB" in r.raw_description)
        assert internal.suggested_type == "transfer"
        assert internal.flag_reason == "uncertain_transfer"

    def test_p2p_transfer_is_left_as_default_expense(self):
        usd = RevolutStatementParser("USD").parse(_content())
        p2p = next(r for r in usd.rows if r.raw_description == "Transfer to SOME PERSON")
        assert p2p.suggested_type is None
        assert p2p.flag_reason is None
        assert p2p.amount < 0

    def test_ordinary_card_payment_untouched(self):
        czk = RevolutStatementParser("CZK").parse(_content())
        assert len(czk.rows) == 1
        assert czk.rows[0].suggested_type is None

    def test_posted_date_is_completed_date_value_date_is_started_date(self):
        pln = RevolutStatementParser("PLN").parse(_content())
        bolt = next(r for r in pln.rows if r.raw_description == "Bolt")
        assert bolt.date_posted == date(2025, 12, 5)
        assert bolt.date_value == date(2025, 12, 4)

    def test_closing_balance_and_period_from_own_currency_only(self):
        pln = RevolutStatementParser("PLN").parse(_content())
        assert pln.period_start == date(2025, 12, 4)
        assert pln.period_end == date(2025, 12, 11)
        assert pln.closing_balance == Decimal("286.74")

    def test_no_matching_rows_yields_empty_statement(self):
        statement = RevolutStatementParser("GBP").parse(_content())
        assert statement.rows == []
        assert statement.period_start is None
        assert statement.closing_balance is None
