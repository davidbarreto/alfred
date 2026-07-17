from datetime import date
from decimal import Decimal

from app.integrations.activobank.statement_parser import ActivoBankStatementParser
from app.integrations.banco_inter.statement_parser import BancoInterStatementParser

_CSV_TEXT = """\
 Extrato Conta Corrente
Conta ;12345678
Período ;01/06/2026 a 30/06/2026
Saldo ;2.345,67

Data Lançamento;Histórico;Descrição;Valor;Saldo
23/06/2026;Pix enviado ;Clinica Exemplo Ltda;-150,01;93,82
23/06/2026;Pix enviado ;Clinica Exemplo Ltda;-120,92;243,83
10/06/2026;Pagamento efetuado;NU PAGAMENTOS SA;-96,99;364,75
10/06/2026;Pagamento efetuado;Fatura cartão Inter;-388,41;461,74
05/06/2026;Pix recebido;Maria Da Silva;1.300,00;850,15
"""


def _content() -> bytes:
    return _CSV_TEXT.encode("utf-8")


class TestCanParse:
    def test_accepts_inter_extrato(self):
        parser = BancoInterStatementParser()
        assert parser.can_parse("Extrato-01-06-2026.csv", _content()) is True

    def test_rejects_activobank_csv(self):
        parser = BancoInterStatementParser()
        content = "HISTÓRICO DE CONTA NÚMERO 456;;;;\n".encode("cp1252")
        assert parser.can_parse("mov456.csv", content) is False

    def test_activobank_parser_rejects_inter_csv(self):
        assert ActivoBankStatementParser().can_parse("Extrato.csv", _content()) is False


class TestParse:
    def test_metadata(self):
        statement = BancoInterStatementParser().parse(_content())
        assert statement.provider == "banco_inter"
        assert statement.account_number == "12345678"
        assert statement.currency == "BRL"
        assert statement.period_start == date(2026, 6, 1)
        assert statement.period_end == date(2026, 6, 30)
        assert statement.closing_balance == Decimal("2345.67")

    def test_joins_historico_and_descricao(self):
        statement = BancoInterStatementParser().parse(_content())
        assert statement.rows[0].raw_description == "Pix enviado - Clinica Exemplo Ltda"
        assert statement.rows[3].raw_description == "Pagamento efetuado - Fatura cartão Inter"

    def test_signs_are_kept_as_is(self):
        statement = BancoInterStatementParser().parse(_content())
        assert statement.rows[0].amount == Decimal("-150.01")
        assert statement.rows[4].amount == Decimal("1300.00")

    def test_running_balance_per_row(self):
        statement = BancoInterStatementParser().parse(_content())
        assert statement.rows[0].balance_after == Decimal("93.82")
        assert statement.rows[1].balance_after == Decimal("243.83")

    def test_identical_rows_disambiguated_by_balance(self):
        statement = BancoInterStatementParser().parse(_content())
        first, second = statement.rows[0], statement.rows[1]
        assert first.date_posted == second.date_posted
        assert first.balance_after != second.balance_after
