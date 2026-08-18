from datetime import date
from decimal import Decimal

from app.integrations.nubank.card_statement_parser import NubankCardStatementParser

_CSV_TEXT = """\
date,title,amount
2025-08-11,Pagamento recebido,"- 1.237,51"
2025-08-05,Amazonprimebr,"19,90"
2025-08-03,Tap Web Vip - Parcela 3/10,"1.187,58"
"""


def _content() -> bytes:
    return _CSV_TEXT.encode("utf-8")


class TestCanParse:
    def test_accepts_nubank_csv(self):
        parser = NubankCardStatementParser()
        assert parser.can_parse("nubank-2025-08.csv", _content()) is True

    def test_rejects_non_csv(self):
        parser = NubankCardStatementParser()
        assert parser.can_parse("nubank.ofx", _content()) is False

    def test_rejects_activobank_csv(self):
        parser = NubankCardStatementParser()
        content = "HISTÓRICO DE CONTA NÚMERO 456;;;;\n".encode("cp1252")
        assert parser.can_parse("mov456.csv", content) is False

    def test_rejects_empty_file(self):
        parser = NubankCardStatementParser()
        assert parser.can_parse("empty.csv", b"") is False


class TestParse:
    def test_metadata(self):
        statement = NubankCardStatementParser().parse(_content())
        assert statement.provider == "nubank_card"
        assert statement.currency == "BRL"
        assert statement.account_number is None
        assert statement.period_start == date(2025, 8, 3)
        assert statement.period_end == date(2025, 8, 11)
        assert statement.closing_balance is None

    def test_purchases_are_negated_to_expenses(self):
        statement = NubankCardStatementParser().parse(_content())
        by_title = {r.raw_description: r for r in statement.rows}
        assert by_title["Amazonprimebr"].amount == Decimal("-19.90")
        assert by_title["Tap Web Vip - Parcela 3/10"].amount == Decimal("-1187.58")

    def test_payment_becomes_positive_inflow(self):
        statement = NubankCardStatementParser().parse(_content())
        payment = next(r for r in statement.rows if r.raw_description == "Pagamento recebido")
        assert payment.amount == Decimal("1237.51")

    def test_single_date_used_for_both_dates(self):
        statement = NubankCardStatementParser().parse(_content())
        first = statement.rows[0]
        assert first.date_posted == first.date_value == date(2025, 8, 11)

    def test_no_running_balance(self):
        statement = NubankCardStatementParser().parse(_content())
        assert all(r.balance_after is None for r in statement.rows)

    def test_header_only_file(self):
        statement = NubankCardStatementParser().parse(b"date,title,amount\n")
        assert statement.rows == []
        assert statement.period_start is None


class TestInstallmentPlanSignals:
    def test_detects_parcela_suffix_as_a_plan_signal(self):
        statement = NubankCardStatementParser().parse(_content())
        assert len(statement.installment_plans_opened) == 1
        signal = statement.installment_plans_opened[0]
        assert signal.plan_ref == "Tap Web Vip"
        assert signal.description == "Tap Web Vip"
        assert signal.total_installments == 10
        assert signal.original_amount is None

    def test_no_signal_for_ordinary_purchases(self):
        content = b"date,title,amount\n2025-08-05,Amazonprimebr,\"19,90\"\n"
        statement = NubankCardStatementParser().parse(content)
        assert statement.installment_plans_opened == []

    def test_dedupes_multiple_installments_of_the_same_plan(self):
        content = (
            b"date,title,amount\n"
            b"2025-07-03,Tap Web Vip - Parcela 2/10,\"1.187,58\"\n"
            b"2025-08-03,Tap Web Vip - Parcela 3/10,\"1.187,58\"\n"
        )
        statement = NubankCardStatementParser().parse(content)
        assert len(statement.installment_plans_opened) == 1
        assert statement.installment_plans_opened[0].total_installments == 10

    def test_distinct_merchants_produce_distinct_signals(self):
        content = (
            b"date,title,amount\n"
            b"2025-08-03,Tap Web Vip - Parcela 3/10,\"1.187,58\"\n"
            b"2025-08-04,Magazine Luiza - Parcela 1/6,\"250,00\"\n"
        )
        statement = NubankCardStatementParser().parse(content)
        refs = {s.plan_ref for s in statement.installment_plans_opened}
        assert refs == {"Tap Web Vip", "Magazine Luiza"}
