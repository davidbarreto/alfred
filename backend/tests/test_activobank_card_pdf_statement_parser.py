from datetime import date
from decimal import Decimal

from app.integrations.activobank.card_pdf_statement_parser import (
    ActivoBankCardPdfStatementParser,
    _parse_text,
    _pdf_text,
)

_PERIOD_START = date(2026, 5, 1)
_PERIOD_END = date(2026, 5, 31)

_STATEMENT_TEXT = """\
EXTRATO VISA CLASSIC ACTIVOBANK N. 2026/005
RESUMO DA CONTA
Extrato de: 2026/05/01 a 2026/05/31 Moeda: EUR
Conta Cartão: 111111-2222222-00-0 Total a Pagar: 500.00
DETALHE DE TRANSAÇÕES COM PAGAMENTO FRACIONADO
MENSALIDADES A PAGAR
Data
Movimento
Descritivo
Valor
Transação
Capital em
Dívida
TAN Plano Capital Juros IS Mensalidade
2026/05/31  COMPRA 4681 SAMPLE SHOP A
 200.00 100.00 9.900% 00001/2 48.00 1.50 0.50 50.00
2026/06/30  COMPRA 4681 SAMPLE SHOP A
 200.00 50.00 9.900% 00001/3 48.00 1.40 0.45 49.85
DETALHE DOS MOVIMENTOS
Data
Movimento
Data
Valor Descritivo Rede Débito Crédito
2026/05/01 2026/05/02 COMPRA 4681 SAMPLE SHOP A 200.00
Fracionada x4 VIS
2026/05/03 2026/05/04 COMPRA 4681 SAMPLE SHOP B 42.50
VIS
2026/05/10 2026/05/10 TAXAS POSTOS COMBUSTIVEL 0.50
2026/05/10 2026/05/10 IMPOSTO DO SELO 0.02
2026/05/15 2026/05/16 TRANSFERENCIA CARTAO CREDITO 9988776 50.00
2026/05/16 2026/05/16 COMISSAO TRANSF CREDITO CONTA A ORDEM 6.00
2026/05/01 2026/05/20 >PAGAMENTO CARTAO DE CREDITO 300.00
2026/05/02 2026/05/21 PAGAMENTO CARTAO CREDITO 100.00
2026/05/31 2026/05/31 JUROS PAG FRACIONADO 1.50
2026/05/31 2026/05/31 IMPOSTO DO SELO 0.50
2026/05/31 2026/05/31 IMP DO SELO S/PAG FRAC 200.00 2.00
TRANSAÇÕES EM MOEDA DIFERENTE DE EUR NA UNIÃO EUROPEIA
Data Transação Valor Câmbio
2026/05/03 COMPRA 4681 SAMPLE SHOP B 4.99
"""


class TestParseTextInstallments:
    """Installment-table parsing and plan-open signal detection are mode-independent --
    exercised here with installments_only=True (the common case); the movements tests
    below cover both modes explicitly."""

    def test_installment_due_this_period_captured_at_capital_amount(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=True)
        row = next(r for r in result.rows if "SAMPLE SHOP A" in r.raw_description)
        assert row.amount == Decimal("-48.00")
        assert row.date_posted == date(2026, 5, 31)
        assert row.raw_description == "COMPRA 4681 SAMPLE SHOP A (00001/2)"
        assert row.installment_juros == Decimal("1.50")
        assert row.installment_duty == Decimal("0.50")
        assert row.flag_reason == "installment_capital"
        assert row.note == "Installment 00001/2"

    def test_future_projected_installment_not_captured(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=True)
        assert all("00001/3" not in r.raw_description for r in result.rows)

    def test_no_period_bounds_yields_no_installment_rows(self):
        result = _parse_text(_STATEMENT_TEXT, None, None, installments_only=True)
        assert all("SAMPLE SHOP A" not in r.raw_description for r in result.rows)

    def test_plan_open_signal_detected(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=True)
        assert len(result.installment_plans_opened) == 1
        signal = result.installment_plans_opened[0]
        assert signal.plan_ref == "00001"
        assert signal.description == "COMPRA 4681 SAMPLE SHOP A"
        assert signal.original_amount == Decimal("-200.00")
        # max(position) across the "00001/2" and "00001/3" rows -- the "Fracionada x4"
        # text in movements is no longer consulted at all (see below).
        assert signal.total_installments == 3

    def test_plan_open_signal_detected_in_full_mode_too(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        assert len(result.installment_plans_opened) == 1

    def test_plan_signal_detected_even_without_a_fracionada_line(self):
        # Regression for the whole point of this redesign: a plan already a few
        # months in (no "Fracionada" announcement in THIS statement's movements at
        # all, since that line only ever appears once, in the long-gone opening
        # month) is still detected purely from the installment schedule table.
        text = _STATEMENT_TEXT.replace(
            "2026/05/01 2026/05/02 COMPRA 4681 SAMPLE SHOP A 200.00\nFracionada x4 VIS\n", ""
        )
        assert "Fracionada" not in text
        result = _parse_text(text, _PERIOD_START, _PERIOD_END, installments_only=True)
        assert len(result.installment_plans_opened) == 1
        assert result.installment_plans_opened[0].plan_ref == "00001"


class TestParseTextMovementsInstallmentsOnly:
    def test_no_ordinary_movements_emitted(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=True)
        # Only the Capital-installment row should be present -- no COMPRA/fees/payments.
        assert len(result.rows) == 1

    def test_fracionado_lump_sum_row_is_skipped(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=True)
        assert all(r.amount != Decimal("-200.00") for r in result.rows)


class TestParseTextMovementsFull:
    def test_fracionado_lump_sum_row_is_skipped(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        assert all(r.amount != Decimal("-200.00") for r in result.rows)

    def test_regular_purchase_is_negative(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        by_desc = {r.raw_description: r for r in result.rows}
        assert by_desc["COMPRA 4681 SAMPLE SHOP B"].amount == Decimal("-42.50")

    def test_installment_juros_and_imposto_recorded_as_own_movements(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        juros = [r for r in result.rows if r.raw_description == "JUROS PAG FRACIONADO"]
        assert len(juros) == 1
        assert juros[0].amount == Decimal("-1.50")
        imposto = [r for r in result.rows if r.raw_description == "IMPOSTO DO SELO"]
        assert len(imposto) == 2
        assert {r.amount for r in imposto} == {Decimal("-0.02"), Decimal("-0.50")}

    def test_installment_capital_plus_movement_taxes_equals_mensalidade(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        capital = next(r for r in result.rows if "SAMPLE SHOP A" in r.raw_description).amount
        juros = next(r for r in result.rows if r.raw_description == "JUROS PAG FRACIONADO").amount
        imposto = next(
            r for r in result.rows
            if r.raw_description == "IMPOSTO DO SELO" and r.amount == Decimal("-0.50")
        ).amount
        assert capital + juros + imposto == Decimal("-50.00")  # matches Mensalidade

    def test_one_time_stamp_duty_on_new_plan_is_kept(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        stamp = next(r for r in result.rows if r.raw_description.startswith("IMP DO SELO S/PAG FRAC"))
        assert stamp.amount == Decimal("-2.00")

    def test_card_payment_is_positive_and_transfer(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        by_desc = {r.raw_description: r for r in result.rows}
        auto = by_desc["PAGAMENTO CARTAO DE CREDITO"]
        assert auto.amount == Decimal("300.00")
        assert auto.suggested_type == "transfer"
        manual = by_desc["PAGAMENTO CARTAO CREDITO"]
        assert manual.amount == Decimal("100.00")
        assert manual.suggested_type == "transfer"

    def test_transfer_out_is_negative_and_transfer(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        transfer = next(
            r for r in result.rows if r.raw_description == "TRANSFERENCIA CARTAO CREDITO 9988776"
        )
        assert transfer.amount == Decimal("-50.00")
        assert transfer.suggested_type == "transfer"

    def test_regular_charges_have_no_suggested_type(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        by_desc = {r.raw_description: r for r in result.rows}
        assert by_desc["COMPRA 4681 SAMPLE SHOP B"].suggested_type is None

    def test_date_posted_uses_data_valor_not_data_movimento(self):
        # Row: "2026/05/03 2026/05/04 COMPRA 4681 SAMPLE SHOP B 42.50" -- Data
        # Movimento is 05/03, Data Valor is 05/04. date_posted (the field the
        # import service treats as the transaction's actual date) must carry
        # Data Valor; date_value keeps Data Movimento.
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        row = next(r for r in result.rows if r.raw_description == "COMPRA 4681 SAMPLE SHOP B")
        assert row.date_posted == date(2026, 5, 4)
        assert row.date_value == date(2026, 5, 3)

    def test_fx_summary_section_is_skipped(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        assert not any(r.amount == Decimal("-4.99") for r in result.rows)

    def test_nothing_parsed_before_movements_section(self):
        text = "2026/01/01 2026/01/01 SHOULD BE IGNORED 1.00\n" + _STATEMENT_TEXT
        result = _parse_text(text, _PERIOD_START, _PERIOD_END, installments_only=False)
        assert all(r.raw_description != "SHOULD BE IGNORED" for r in result.rows)

    def test_no_balance_after(self):
        result = _parse_text(_STATEMENT_TEXT, _PERIOD_START, _PERIOD_END, installments_only=False)
        assert all(r.balance_after is None for r in result.rows)


class TestPdfText:
    def test_returns_none_without_pdf_marker(self):
        assert _pdf_text(b"\x00\x00\x00 not a pdf") is None

    def test_returns_none_for_corrupt_pdf_body(self):
        assert _pdf_text(b"%PDF-1.7 garbage") is None


class TestCanParse:
    def test_rejects_non_pdf_extension(self):
        parser = ActivoBankCardPdfStatementParser(installments_only=True)
        assert parser.can_parse("statement.csv", b"%PDF-1.7") is False

    def test_rejects_bytes_without_marker(self):
        parser = ActivoBankCardPdfStatementParser(installments_only=True)
        assert parser.can_parse("statement.pdf", b"\x00\x00\x00\x00") is False

    def test_full_mode_is_never_auto_detected(self):
        parser = ActivoBankCardPdfStatementParser(installments_only=False)
        assert parser.can_parse("statement.pdf", b"%PDF-1.7 " + _STATEMENT_TEXT.encode()) is False


class TestParse:
    def test_installments_only_provider_name(self):
        assert ActivoBankCardPdfStatementParser(installments_only=True).provider == "activobank_card_pdf"

    def test_full_provider_name(self):
        assert (
            ActivoBankCardPdfStatementParser(installments_only=False).provider
            == "activobank_card_pdf_full"
        )

    def test_parse_via_mocked_text_installments_only(self, monkeypatch):
        import app.integrations.activobank.card_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankCardPdfStatementParser(installments_only=True).parse(b"%PDF fake")

        assert statement.provider == "activobank_card_pdf"
        assert statement.currency == "EUR"
        assert statement.account_number == "111111-2222222-00-0"
        assert statement.period_start == _PERIOD_START
        assert statement.period_end == _PERIOD_END
        assert statement.closing_balance is None
        assert len(statement.rows) == 1
        assert len(statement.installment_plans_opened) == 1

    def test_parse_via_mocked_text_full(self, monkeypatch):
        import app.integrations.activobank.card_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: _STATEMENT_TEXT)

        statement = ActivoBankCardPdfStatementParser(installments_only=False).parse(b"%PDF fake")

        assert statement.provider == "activobank_card_pdf_full"
        assert len(statement.rows) == 11
        assert len(statement.installment_plans_opened) == 1

    def test_unreadable_pdf_yields_empty_statement(self, monkeypatch):
        import app.integrations.activobank.card_pdf_statement_parser as module

        monkeypatch.setattr(module, "_pdf_text", lambda content: None)

        statement = ActivoBankCardPdfStatementParser().parse(b"%PDF fake")

        assert statement.rows == []
        assert statement.installment_plans_opened == []
