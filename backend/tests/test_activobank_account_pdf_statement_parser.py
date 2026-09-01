from datetime import date
from decimal import Decimal

from app.integrations.activobank.account_pdf_statement_parser import (
    ActivoBankAccountPdfStatementParser,
    _pdf_text,
)

_STATEMENT_TEXT = """\
CE00000/01
Banco ActivoBank, S.A. - Sede: Rua Augusta, 84, 1100-053 Lisboa
Capital Social: Euros 127.600.000 - Matric. na Cons. do Registo Com. de Lisboa, com o nº único de matrícula e de identificação fiscal 500 734 305
25/06/30 EXT. N. 2025/006 DEPOSITO A ORDEM: 99999999999
EXTRATO COMBINADO
MOEDA BASE: EURO
RESUMO DAS CONTAS
CONTA SIMPLES 1 000.00
CONTA POUPEUP 500.00
CONTA CARTAO 50.00-
Banco ActivoBank, S.A. - Sede: Rua Augusta, 84, 1100-053 Lisboa
Capital Social: Euros 127.600.000 - Matric. na Cons. do Registo Com. de Lisboa, com o nº único de matrícula e de identificação fiscal 500 734 305
25/06/30 EXT. N. 2025/006 DEPOSITO A ORDEM: 99999999999 PAG: 00002
CONTA SIMPLES N. 99999999999 MOEDA: EUR
EXTRATO DE 2025/06/02 A 2025/06/30
DATA
LANC.
DATA
VALOR DESCRITIVO DEBITO CREDITO SALDO
SALDO INICIAL 1 000.00
6.02 6.02
COMPRA 1234 SAMPLE SHOP A CONTACTLESS 100.00 900.00
6.03 6.03 TRF DE Emergency fund 200.00 1 100.00
6.04 6.04 COMPRA 1234 SAMPLE SHOP B CONTACTLESS 50.00 1 050.00
A TRANSPORTAR 1 050.00
Banco ActivoBank, S.A. - Sede: Rua Augusta, 84, 1100-053 Lisboa
Capital Social: Euros 127.600.000 - Matric. na Cons. do Registo Com. de Lisboa, com o nº único de matrícula e de identificação fiscal 500 734 305
25/06/30 EXT. N. 2025/006 DEPOSITO A ORDEM: 99999999999 PAG: 00003
TRANSPORTE 1 050.00
6.05 6.05
COMPRA 5678 SAMPLE SHOP C CONTACTLESS 25.00 1 025.00
6.30 6.30 TRANSFERENCIA - VENCIMENTO 500.00 1 525.00
SALDO FINAL 1 525.00
SALDO DISPONIVEL 1 525.00
CONTA POUPEUP N. 11111111111 MOEDA: EUR
EXTRATO DE 2025/06/02 A 2025/06/30
DATA
LANC.
DATA
VALOR DESCRITIVO DEBITO CREDITO SALDO
SALDO INICIAL 500.00
6.10 6.10 TRF P/ SOMEONE ELSE 100.00 400.00
SALDO FINAL 400.00
SALDO DISPONIVEL 400.00
"""


class TestPdfText:
    def test_returns_none_without_pdf_marker(self):
        assert _pdf_text(b"\x00\x00\x00 not a pdf") is None

    def test_returns_none_for_corrupt_pdf_body(self):
        assert _pdf_text(b"%PDF-1.7 garbage") is None


class TestCanParse:
    def test_never_auto_detected(self):
        parser = ActivoBankAccountPdfStatementParser()
        assert parser.can_parse("statement.pdf", ("%PDF-1.7 " + _STATEMENT_TEXT).encode()) is False


class TestParse:
    def test_provider_name(self):
        assert ActivoBankAccountPdfStatementParser().provider == "activobank_account_pdf"

    def test_metadata(self, monkeypatch):
        import app.integrations.activobank.account_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankAccountPdfStatementParser().parse(b"%PDF fake")

        assert statement.provider == "activobank_account_pdf"
        assert statement.account_number == "99999999999"
        assert statement.currency == "EUR"
        assert statement.period_start == date(2025, 6, 2)
        assert statement.period_end == date(2025, 6, 30)
        assert statement.closing_balance == Decimal("1525.00")

    def test_only_conta_simples_rows_are_emitted(self, monkeypatch):
        import app.integrations.activobank.account_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankAccountPdfStatementParser().parse(b"%PDF fake")

        assert len(statement.rows) == 5
        assert all("SOMEONE ELSE" not in r.raw_description for r in statement.rows)

    def test_page_break_split_row_is_reassembled(self, monkeypatch):
        import app.integrations.activobank.account_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankAccountPdfStatementParser().parse(b"%PDF fake")

        first = statement.rows[0]
        assert first.raw_description == "COMPRA 1234 SAMPLE SHOP A CONTACTLESS"
        assert first.date_posted == date(2025, 6, 2)
        assert first.amount == Decimal("-100.00")
        assert first.balance_after == Decimal("900.00")

    def test_sign_derived_from_balance_delta_for_debit_and_credit(self, monkeypatch):
        import app.integrations.activobank.account_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankAccountPdfStatementParser().parse(b"%PDF fake")
        by_desc = {r.raw_description: r for r in statement.rows}

        assert by_desc["TRF DE Emergency fund"].amount == Decimal("200.00")
        assert by_desc["COMPRA 1234 SAMPLE SHOP B CONTACTLESS"].amount == Decimal("-50.00")
        assert by_desc["TRANSFERENCIA - VENCIMENTO"].amount == Decimal("500.00")

    def test_transportar_continuation_rows_are_not_emitted(self, monkeypatch):
        import app.integrations.activobank.account_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankAccountPdfStatementParser().parse(b"%PDF fake")
        assert all(r.amount != Decimal("1050.00") for r in statement.rows)

    def test_balances_reconcile_across_all_rows(self, monkeypatch):
        import app.integrations.activobank.account_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankAccountPdfStatementParser().parse(b"%PDF fake")
        balance = Decimal("1000.00")
        for row in statement.rows:
            balance += row.amount
            assert balance == row.balance_after

    def test_unreadable_pdf_yields_empty_statement(self, monkeypatch):
        import app.integrations.activobank.account_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: None)

        statement = ActivoBankAccountPdfStatementParser().parse(b"%PDF fake")

        assert statement.rows == []
        assert statement.account_number is None
