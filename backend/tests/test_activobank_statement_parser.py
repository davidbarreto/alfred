from datetime import date
from decimal import Decimal

from app.integrations.activobank.statement_parser import ActivoBankStatementParser

_CSV_TEXT = """\
HISTÓRICO DE CONTA NÚMERO 45636653703;;;;
Moeda:;EUR;;;
;;;;
Tipo:;Todos;;;
Data de:;01/06/2026;;;
Data até:;30/06/2026;;;
;;;;
Data Lanc.;Data Valor;Descrição;Valor;Saldo
01/06/2026;01/06/2026;COMPRA 2876 NO PORTO PRODUCOES VILA CONTACTLESS;-5,00;2 859,03
01/06/2026;01/06/2026;TRF P/ Antonio Ismael;-1 200,00;1 361,08
18/06/2026;18/06/2026;TRF DE PoupeUp - Moneybox;1 000,00;1 087,48
30/06/2026;30/06/2026;TRANSFERENCIA - VENCIMENTO;3 878,41;4 188,02
30/06/2026;01/07/2026;IMPOSTO SELO, ART 17.3.1;-0,01;2 539,65
"""


def _content() -> bytes:
    return _CSV_TEXT.encode("cp1252")


class TestCanParse:
    def test_accepts_activobank_csv(self):
        parser = ActivoBankStatementParser()
        assert parser.can_parse("mov45636653703.csv", _content()) is True

    def test_rejects_non_csv_extension(self):
        parser = ActivoBankStatementParser()
        assert parser.can_parse("statement.pdf", _content()) is False

    def test_rejects_unrelated_csv(self):
        parser = ActivoBankStatementParser()
        assert parser.can_parse("other.csv", b"col1,col2\n1,2\n") is False


class TestParse:
    def test_metadata(self):
        statement = ActivoBankStatementParser().parse(_content())
        assert statement.provider == "activobank"
        assert statement.account_number == "45636653703"
        assert statement.currency == "EUR"
        assert statement.period_start == date(2026, 6, 1)
        assert statement.period_end == date(2026, 6, 30)

    def test_rows_parsed(self):
        statement = ActivoBankStatementParser().parse(_content())
        assert len(statement.rows) == 5
        first = statement.rows[0]
        assert first.date_posted == date(2026, 6, 1)
        assert first.raw_description == "COMPRA 2876 NO PORTO PRODUCOES VILA CONTACTLESS"
        assert first.amount == Decimal("-5.00")
        assert first.balance_after == Decimal("2859.03")

    def test_thousand_separator_amounts(self):
        statement = ActivoBankStatementParser().parse(_content())
        assert statement.rows[1].amount == Decimal("-1200.00")
        assert statement.rows[2].amount == Decimal("1000.00")
        assert statement.rows[3].amount == Decimal("3878.41")

    def test_value_date_differs_from_posted_date(self):
        statement = ActivoBankStatementParser().parse(_content())
        last = statement.rows[-1]
        assert last.date_posted == date(2026, 6, 30)
        assert last.date_value == date(2026, 7, 1)

    def test_closing_balance_is_last_row_balance(self):
        statement = ActivoBankStatementParser().parse(_content())
        assert statement.closing_balance == Decimal("2539.65")

    def test_utf8_content_also_parses(self):
        statement = ActivoBankStatementParser().parse(_CSV_TEXT.encode("utf-8"))
        assert len(statement.rows) == 5

    def test_empty_body(self):
        header_only = "\n".join(_CSV_TEXT.splitlines()[:8]) + "\n"
        statement = ActivoBankStatementParser().parse(header_only.encode("cp1252"))
        assert statement.rows == []
        assert statement.closing_balance is None
