from datetime import date
from decimal import Decimal

from app.integrations.wise.statement_parser import WiseStatementParser

_HEADER = (
    'ID,Status,Direction,"Created on","Finished on","Source fee amount",'
    '"Source fee currency","Target fee amount","Target fee currency","Source name",'
    '"Source amount (after fees)","Source currency","Target name",'
    '"Target amount (after fees)","Target currency","Exchange rate",'
    'Reference,Batch,"Created by",Category,Note'
)

_CSV_TEXT = (
    _HEADER
    + "\n"
    + '\n'.join(
        [
            'CARD_TRANSACTION-0000000001,COMPLETED,OUT,"2026-06-01 10:00:00","2026-06-01 10:00:00",0.00,EUR,,,"SOME PERSON",12.50,EUR,"SOME SHOP",12.50,EUR,1.0,,,"SOME PERSON",Shopping,',
            'TRANSFER-0000000002,COMPLETED,OUT,"2026-06-02 23:50:00","2026-06-03 00:05:00",1.00,EUR,,,"SOME PERSON",50.00,EUR,"SOME PERSON",300.00,BRL,6.0,,,"SOME PERSON",General,',
            'TRANSFER-0000000003,COMPLETED,IN,"2026-06-03 08:00:00","2026-06-03 08:01:00",0.50,EUR,,,"SOME PERSON",100.00,EUR,"SOME PERSON",100.00,EUR,1.0,,,"SOME PERSON","Money added",',
            'TRANSFER-0000000004,COMPLETED,OUT,"2026-06-04 08:00:00","2026-06-04 08:01:00",0.00,EUR,,,"SOME PERSON",25.00,EUR,"SOME PERSON",25.00,EUR,1.0,,,"SOME PERSON","Money sent out",',
            'TRANSFER-0000000005,COMPLETED,IN,"2026-06-05 08:00:00","2026-06-05 08:02:00",0.00,EUR,,,"ANOTHER PERSON",40.00,EUR,"SOME PERSON",40.00,EUR,1.0,,,"SOME PERSON",General,',
            'TRANSFER-0000000006,PENDING,OUT,"2026-06-06 08:00:00","",0.00,EUR,,,"SOME PERSON",10.00,EUR,"SOME PERSON",10.00,EUR,1.0,,,"SOME PERSON",General,',
        ]
    )
    + "\n"
)


def _content() -> bytes:
    return _CSV_TEXT.encode("utf-8")


class TestCanParse:
    def test_accepts_matching_header(self):
        parser = WiseStatementParser()
        assert parser.can_parse("wise.csv", _content()) is True

    def test_rejects_non_csv_extension(self):
        parser = WiseStatementParser()
        assert parser.can_parse("wise.pdf", _content()) is False

    def test_rejects_unrelated_csv(self):
        parser = WiseStatementParser()
        assert parser.can_parse("other.csv", b"col1,col2\n1,2\n") is False

    def test_provider_name(self):
        assert WiseStatementParser().provider == "wise"


class TestParse:
    def test_metadata(self):
        statement = WiseStatementParser().parse(_content())
        assert statement.provider == "wise"
        assert statement.account_number is None
        assert statement.closing_balance is None

    def test_pending_rows_are_excluded(self):
        statement = WiseStatementParser().parse(_content())
        assert all("0000000006" not in r.raw_description for r in statement.rows)
        assert len(statement.rows) == 6  # 5 completed rows, one of which splits into 2 legs

    def test_card_purchase_is_a_single_expense_leg(self):
        statement = WiseStatementParser().parse(_content())
        purchase = next(r for r in statement.rows if r.raw_description == "SOME SHOP")
        assert purchase.amount == Decimal("-12.50")
        assert purchase.currency == "EUR"
        assert purchase.suggested_type is None

    def test_conversion_splits_into_two_transfer_legs(self):
        statement = WiseStatementParser().parse(_content())
        out_leg = next(r for r in statement.rows if r.raw_description == "Currency exchange to BRL")
        in_leg = next(r for r in statement.rows if r.raw_description == "Currency exchange from EUR")
        assert out_leg.amount == Decimal("-50.00")
        assert out_leg.currency == "EUR"
        assert out_leg.suggested_type == "transfer"
        assert in_leg.amount == Decimal("300.00")
        assert in_leg.currency == "BRL"
        assert in_leg.suggested_type == "transfer"

    def test_conversion_uses_finished_date_for_posting_and_created_for_value(self):
        statement = WiseStatementParser().parse(_content())
        out_leg = next(r for r in statement.rows if r.raw_description == "Currency exchange to BRL")
        assert out_leg.date_posted == date(2026, 6, 3)
        assert out_leg.date_value == date(2026, 6, 2)

    def test_topup_is_a_transfer_not_income(self):
        statement = WiseStatementParser().parse(_content())
        topup = next(r for r in statement.rows if r.raw_description == "Money added")
        assert topup.amount == Decimal("100.00")
        assert topup.currency == "EUR"
        assert topup.suggested_type == "transfer"

    def test_withdrawal_is_a_transfer_not_expense(self):
        statement = WiseStatementParser().parse(_content())
        withdrawal = next(r for r in statement.rows if r.raw_description == "Money sent out")
        assert withdrawal.amount == Decimal("-25.00")
        assert withdrawal.currency == "EUR"
        assert withdrawal.suggested_type == "transfer"

    def test_third_party_inbound_payment_uses_target_leg(self):
        statement = WiseStatementParser().parse(_content())
        received = next(r for r in statement.rows if r.raw_description == "ANOTHER PERSON")
        assert received.amount == Decimal("40.00")
        assert received.currency == "EUR"
        assert received.suggested_type is None

    def test_posted_at_carries_the_raw_finished_timestamp(self):
        statement = WiseStatementParser().parse(_content())
        purchase = next(r for r in statement.rows if r.raw_description == "SOME SHOP")
        assert purchase.posted_at == "2026-06-01 10:00:00"

    def test_period_spans_completed_rows_only(self):
        statement = WiseStatementParser().parse(_content())
        assert statement.period_start == date(2026, 6, 1)
        assert statement.period_end == date(2026, 6, 5)

    def test_empty_file_yields_empty_statement(self):
        statement = WiseStatementParser().parse((_HEADER + "\n").encode("utf-8"))
        assert statement.rows == []
        assert statement.period_start is None
