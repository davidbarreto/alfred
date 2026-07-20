from datetime import date
from decimal import Decimal

from app.integrations.banco_inter.fatura_parser import (
    BancoInterFaturaParser,
    _parse_text,
    _pdf_text,
)

_FATURA_TEXT = """\
Resumo da fatura
Total da sua fatura
R$ 388,41
Limite de crédito total
R$ 8.300,00
Data de Vencimento
15/06/2026
Despesas da fatura
CARTÃO 1234****5678
Data Movimentação Beneficiário Valor
15 de mai. 2026 PAGTO DEBITO AUTOMATICO - + R$ 388,41
Total CARTÃO 1234****5678 R$ 0,00
CARTÃO 1234****9012
Data Movimentação Beneficiário Valor
12 de out. 2025 LOJA DE BRINQUEDOS XY (Parcela 08 de 10) - R$ 57,04
20 de mar. 2026 CURSO ONLINE ABC (Parcela 03 de 10) - R$ 99,75
09 de mai. 2026 NETFLIX.COM - R$ 44,90
Total CARTÃO 1234****9012 R$ 201,69
"""


class TestParseText:
    def test_charges_are_negative(self):
        rows = _parse_text(_FATURA_TEXT)
        by_desc = {r.raw_description: r for r in rows}
        assert by_desc["NETFLIX.COM"].amount == Decimal("-44.90")
        assert by_desc["LOJA DE BRINQUEDOS XY (Parcela 08 de 10)"].amount == Decimal("-57.04")

    def test_payment_is_positive(self):
        rows = _parse_text(_FATURA_TEXT)
        payment = next(r for r in rows if r.raw_description == "PAGTO DEBITO AUTOMATICO")
        assert payment.amount == Decimal("388.41")

    def test_payment_is_suggested_as_transfer_not_income(self):
        rows = _parse_text(_FATURA_TEXT)
        payment = next(r for r in rows if r.raw_description == "PAGTO DEBITO AUTOMATICO")
        assert payment.suggested_type == "transfer"

    def test_charges_have_no_suggested_type(self):
        rows = _parse_text(_FATURA_TEXT)
        charge = next(r for r in rows if r.raw_description == "NETFLIX.COM")
        assert charge.suggested_type is None

    def test_portuguese_month_names(self):
        rows = _parse_text(_FATURA_TEXT)
        dates = {r.raw_description: r.date_posted for r in rows}
        assert dates["PAGTO DEBITO AUTOMATICO"] == date(2026, 5, 15)
        assert dates["LOJA DE BRINQUEDOS XY (Parcela 08 de 10)"] == date(2025, 10, 12)

    def test_parse_text_alone_does_not_redate(self):
        rows = _parse_text(_FATURA_TEXT)
        assert all(r.flag_reason is None for r in rows)

    def test_total_and_header_lines_skipped(self):
        rows = _parse_text(_FATURA_TEXT)
        assert len(rows) == 4

    def test_nothing_parsed_before_despesas_section(self):
        text = "15 de mai. 2026 SHOULD BE IGNORED - R$ 10,00\n" + _FATURA_TEXT
        rows = _parse_text(text)
        assert all(r.raw_description != "SHOULD BE IGNORED" for r in rows)


class TestPdfText:
    def test_returns_none_without_pdf_marker(self):
        assert _pdf_text(b"\x00\x00\x00 not a pdf") is None

    def test_returns_none_for_corrupt_pdf_body(self):
        assert _pdf_text(b"%PDF-1.7 garbage") is None


class TestCanParse:
    def test_rejects_non_pdf_extension(self):
        parser = BancoInterFaturaParser()
        assert parser.can_parse("fatura.csv", b"%PDF-1.7") is False

    def test_rejects_bytes_without_marker(self):
        parser = BancoInterFaturaParser()
        assert parser.can_parse("fatura.pdf", b"\x00\x00\x00\x00") is False


class TestParse:
    def test_parse_via_mocked_text(self, monkeypatch):
        import app.integrations.banco_inter.fatura_parser as module
        monkeypatch.setattr(module, "_pdf_text", lambda content: _FATURA_TEXT)

        statement = BancoInterFaturaParser().parse(b"%PDF fake")

        assert statement.provider == "banco_inter_card"
        assert statement.currency == "BRL"
        assert statement.account_number == "1234****5678"
        assert statement.period_end == date(2026, 6, 15)
        assert statement.closing_balance is None
        assert len(statement.rows) == 4

    def test_old_installments_redated_to_fatura_month_and_flagged(self, monkeypatch):
        import app.integrations.banco_inter.fatura_parser as module
        monkeypatch.setattr(module, "_pdf_text", lambda content: _FATURA_TEXT)

        statement = BancoInterFaturaParser().parse(b"%PDF fake")
        by_desc = {r.raw_description: r for r in statement.rows}

        old = by_desc["LOJA DE BRINQUEDOS XY (Parcela 08 de 10)"]
        assert old.date_posted == date(2026, 6, 1)
        assert old.date_value == date(2025, 10, 12)  # printed date kept for dedup
        assert old.flag_reason == "redated_installment"

        march = by_desc["CURSO ONLINE ABC (Parcela 03 de 10)"]
        assert march.date_posted == date(2026, 6, 1)
        assert march.flag_reason == "redated_installment"

    def test_recent_rows_keep_printed_dates(self, monkeypatch):
        import app.integrations.banco_inter.fatura_parser as module
        monkeypatch.setattr(module, "_pdf_text", lambda content: _FATURA_TEXT)

        statement = BancoInterFaturaParser().parse(b"%PDF fake")
        by_desc = {r.raw_description: r for r in statement.rows}

        assert by_desc["NETFLIX.COM"].date_posted == date(2026, 5, 9)
        assert by_desc["NETFLIX.COM"].flag_reason is None
        assert by_desc["PAGTO DEBITO AUTOMATICO"].date_posted == date(2026, 5, 15)
        assert by_desc["PAGTO DEBITO AUTOMATICO"].flag_reason is None

    def test_unreadable_pdf_yields_empty_statement(self, monkeypatch):
        import app.integrations.banco_inter.fatura_parser as module
        monkeypatch.setattr(module, "_pdf_text", lambda content: None)

        statement = BancoInterFaturaParser().parse(b"%PDF fake")

        assert statement.rows == []
