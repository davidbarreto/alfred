from datetime import date
from decimal import Decimal

from app.integrations.activobank.card_statement_parser import ActivoBankCardStatementParser
from app.integrations.activobank.statement_parser import ActivoBankStatementParser

_CSV_TEXT = """\
Movimentos a Crédito na Conta Cartão Número 4544963354476000;;;;
Moeda:;EUR;;;
Conta à Ordem:;45636653703;;;
Data de:;01/06/2026;;;
Data até:;30/06/2026;;;
;;;;
Data Lanc.;Data Valor;Descrição;Valor;
31/05/2026;01/06/2026;COMPRA 4681 FNAC NORTESHOPPING 4460 CONT;135,33;
06/06/2026;18/06/2026;COMPRA 4681 IKEA MATOSINHOS CAIXAS ECMAT;428,83;
01/06/2026;23/06/2026; PAGAMENTO CARTAO DE CREDITO;-1 374,06;
29/06/2026;29/06/2026;IMPOSTO DO SELO;0,02;
30/06/2026;30/06/2026;IMPOSTO DO SELO;0,04;
"""


def _content() -> bytes:
    return "﻿".encode("utf-8") + _CSV_TEXT.encode("utf-8")


class TestCanParse:
    def test_accepts_card_csv(self):
        parser = ActivoBankCardStatementParser()
        assert parser.can_parse("movCard4544963354476000.csv", _content()) is True

    def test_rejects_account_history_csv(self):
        parser = ActivoBankCardStatementParser()
        account_csv = "HISTÓRICO DE CONTA NÚMERO 456;;;;\n".encode("cp1252")
        assert parser.can_parse("mov456.csv", account_csv) is False

    def test_account_parser_rejects_card_csv(self):
        assert ActivoBankStatementParser().can_parse("movCard.csv", _content()) is False


class TestParse:
    def test_metadata(self):
        statement = ActivoBankCardStatementParser().parse(_content())
        assert statement.provider == "activobank_card"
        assert statement.account_number == "4544963354476000"
        assert statement.currency == "EUR"
        assert statement.period_start == date(2026, 6, 1)
        assert statement.period_end == date(2026, 6, 30)
        assert statement.closing_balance is None

    def test_purchases_are_negated_to_expenses(self):
        statement = ActivoBankCardStatementParser().parse(_content())
        assert statement.rows[0].amount == Decimal("-135.33")
        assert statement.rows[1].amount == Decimal("-428.83")

    def test_payment_becomes_positive_inflow(self):
        statement = ActivoBankCardStatementParser().parse(_content())
        payment = statement.rows[2]
        assert payment.raw_description == "PAGAMENTO CARTAO DE CREDITO"
        assert payment.amount == Decimal("1374.06")

    def test_no_running_balance(self):
        statement = ActivoBankCardStatementParser().parse(_content())
        assert all(r.balance_after is None for r in statement.rows)

    def test_posted_date_outside_period_kept(self):
        statement = ActivoBankCardStatementParser().parse(_content())
        assert statement.rows[0].date_posted == date(2026, 5, 31)
        assert statement.rows[0].date_value == date(2026, 6, 1)
