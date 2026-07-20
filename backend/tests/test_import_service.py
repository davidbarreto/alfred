import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.features.core.embeddings.schemas import EmbeddingSearchResult
from app.features.finance.imports.schemas import (
    ImportCommitGroupedRequest,
    ImportCommitGroupedRow,
    ImportCommitRequest,
    ImportCommitRow,
    ImportRuleFilters,
    ImportRuleUpdate,
)
from app.features.finance.imports.service import (
    ImportService,
    InvalidGroupedImportError,
    _clean_description,
    _compute_dedup_hash,
    _extract_json,
    _rule_matches,
)
from app.features.finance.imports.tables import ImportBatch, ImportRule
from app.shared.llm import LlmResponse
from app.shared.statement import ParsedRow, ParsedStatement


def _row(**kwargs) -> ParsedRow:
    defaults = dict(
        date_posted=date(2026, 6, 1),
        date_value=date(2026, 6, 1),
        raw_description="COMPRA 8597 PINGO DOCE CIRCUNVALPOR CONTACTLESS",
        amount=Decimal("-23.17"),
        currency="EUR",
        balance_after=Decimal("471.09"),
    )
    defaults.update(kwargs)
    return ParsedRow(**defaults)


def _rule(**kwargs) -> ImportRule:
    defaults = dict(
        id=1,
        pattern="PINGO DOCE",
        amount=None,
        mode="auto",
        description="Pingo Doce",
        merchant="Pingo Doce",
        category_id=10,
        transfer_account_id=None,
        position=0,
    )
    defaults.update(kwargs)
    rule = ImportRule()
    for key, value in defaults.items():
        setattr(rule, key, value)
    return rule


class _FakeParser:
    provider = "fakebank"

    def __init__(self, statement: ParsedStatement) -> None:
        self._statement = statement

    def can_parse(self, filename: str, content: bytes) -> bool:
        return filename.endswith(".csv")

    def parse(self, content: bytes) -> ParsedStatement:
        return self._statement


def _statement(rows: list[ParsedRow]) -> ParsedStatement:
    return ParsedStatement(
        provider="fakebank",
        account_number="123",
        currency="EUR",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        closing_balance=Decimal("2539.65"),
        rows=rows,
    )


def _category(cat_id: int, name: str):
    cat = MagicMock()
    cat.id = cat_id
    cat.name = name
    return cat


def _account(account_id: int, name: str, currency: str):
    a = MagicMock()
    a.id = account_id
    a.name = name
    a.currency = currency
    return a


def _service(statement: ParsedStatement | None = None, llm=None, files=None) -> ImportService:
    service = ImportService(
        session=AsyncMock(),
        parsers={"fakebank": _FakeParser(statement or _statement([]))},
        embedding_service=AsyncMock(),
        llm_provider=llm,
        file_storage=files,
    )
    service._repo = AsyncMock()
    service._txn_repo = AsyncMock()
    service._category_repo = AsyncMock()
    service._account_repo = AsyncMock()
    service._repo.list_rules.return_value = []
    service._repo.add_rule = MagicMock()
    # session.add() is sync on a real AsyncSession; AsyncMock would otherwise turn it
    # into a coroutine-returning attribute that nothing awaits.
    service._session.add = MagicMock()
    service._txn_repo.get_existing_dedup_hashes.return_value = set()
    service._category_repo.list.return_value = []
    service._account_repo.list.return_value = []
    service._embeddings.search.return_value = []
    return service


class TestCleanDescription:
    def test_strips_card_purchase_noise(self):
        assert (
            _clean_description("COMPRA 8597 PINGO DOCE CIRCUNVALPOR CONTACTLESS")
            == "PINGO DOCE CIRCUNVALPOR"
        )

    def test_strips_mbway_prefix(self):
        assert _clean_description("TRF MB WAY P/ ALAN GARCIA") == "ALAN GARCIA"

    def test_strips_direct_debit_prefix(self):
        assert _clean_description("DD EDP COMERCIAL  16010012887808 PT34100781").startswith(
            "EDP COMERCIAL"
        )

    def test_strips_postal_code(self):
        assert "1643-001" not in _clean_description(
            "COMPRA 8597 PAYSHOP PORTUGAL SA 1643-001 LISBOA"
        )


class TestDedupHash:
    def test_stable_for_same_row(self):
        assert _compute_dedup_hash(1, _row(), 1) == _compute_dedup_hash(1, _row(), 1)

    def test_differs_by_account(self):
        assert _compute_dedup_hash(1, _row(), 1) != _compute_dedup_hash(2, _row(), 1)

    def test_identical_rows_different_balance_get_different_hashes(self):
        row_a = _row(balance_after=Decimal("997.07"))
        row_b = _row(balance_after=Decimal("996.27"))
        assert _compute_dedup_hash(1, row_a, 1) != _compute_dedup_hash(1, row_b, 1)

    def test_occurrence_fallback_when_no_balance(self):
        row = _row(balance_after=None)
        assert _compute_dedup_hash(1, row, 1) != _compute_dedup_hash(1, row, 2)

    def test_same_day_same_amount_same_balance_disambiguated_by_posted_at(self):
        # Regression: two real top-ups on the same day, for the same amount, with an
        # Exchange in between spending each one back down to zero -- same date, same
        # description, same amount, and coincidentally the same balance_after too.
        # Without posted_at these hash identically and the second is wrongly flagged
        # as an in-file duplicate.
        morning = _row(posted_at="2025-12-05 08:01:14")
        afternoon = _row(posted_at="2025-12-05 15:57:40")
        assert _compute_dedup_hash(1, morning, 1) != _compute_dedup_hash(1, afternoon, 2)

    def test_identical_posted_at_still_collides(self):
        # A genuine repeated line (overlapping export windows) has the same timestamp
        # down to the second, so it must still be caught as a duplicate.
        row_a = _row(posted_at="2025-12-05 08:01:14")
        row_b = _row(posted_at="2025-12-05 08:01:14")
        assert _compute_dedup_hash(1, row_a, 1) == _compute_dedup_hash(1, row_b, 1)


class TestRuleMatches:
    def test_case_insensitive_substring(self):
        assert _rule_matches(_rule(), "compra 8597 pingo doce sao mamede", Decimal("-5")) is True

    def test_no_match(self):
        assert _rule_matches(_rule(), "CONTINENTE BOM DIA", Decimal("-5")) is False

    def test_amount_constrained_rule(self):
        rule = _rule(pattern="PAYSHOP", amount=Decimal("-10.00"))
        assert _rule_matches(rule, "COMPRA 8597 PAYSHOP PORTUGAL", Decimal("-10.00")) is True
        assert _rule_matches(rule, "COMPRA 8597 PAYSHOP PORTUGAL", Decimal("-25.00")) is False


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"items": []}') == {"items": []}

    def test_fenced_json(self):
        assert _extract_json('```json\n{"items": [1]}\n```') == {"items": [1]}

    def test_garbage(self):
        assert _extract_json("no json here") is None


class TestPreview:
    @pytest.mark.asyncio
    async def test_unknown_provider_returns_none(self):
        service = _service()
        assert await service.preview(1, "x.csv", b"", provider="nope") is None

    @pytest.mark.asyncio
    async def test_marks_duplicates(self):
        rows = [_row(), _row(balance_after=Decimal("400.00"))]
        service = _service(_statement(rows))
        dup_hash = _compute_dedup_hash(1, rows[0], 1)
        service._txn_repo.get_existing_dedup_hashes.return_value = {dup_hash}

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.duplicate_count == 1
        assert preview.new_count == 1
        assert preview.rows[0].status == "duplicate"
        assert preview.rows[0].duplicate_reason == "already_imported"
        assert preview.rows[1].status == "new"

    @pytest.mark.asyncio
    async def test_marks_rows_repeated_within_the_same_file(self):
        # Overlapping export date ranges can produce the exact same source line twice
        # in one file, before either has ever been imported -- this must be caught at
        # preview time, not silently dropped at commit with no visible explanation.
        rows = [_row(), _row()]
        service = _service(_statement(rows))

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].status == "new"
        assert preview.rows[1].status == "duplicate"
        assert preview.rows[1].duplicate_reason == "repeated_in_file"
        assert preview.new_count == 1
        assert preview.duplicate_count == 1

    @pytest.mark.asyncio
    async def test_does_not_flag_coincidental_same_balance_rows_as_duplicates(self):
        # Regression for the Revolut top-up scenario: two distinct top-ups on the same
        # day, same amount, same description, whose balance coincidentally matches
        # because each was spent back down to zero by an Exchange in between. These are
        # real, separate transactions and must both come through as "new".
        rows = [
            _row(
                raw_description="Apple Pay top-up by *7098",
                amount=Decimal("200.00"),
                balance_after=Decimal("200.00"),
                posted_at="2025-12-05 08:01:14",
            ),
            _row(
                raw_description="Apple Pay top-up by *7098",
                amount=Decimal("200.00"),
                balance_after=Decimal("200.00"),
                posted_at="2025-12-05 15:57:40",
            ),
        ]
        service = _service(_statement(rows))

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].status == "new"
        assert preview.rows[1].status == "new"
        assert preview.new_count == 2
        assert preview.duplicate_count == 0

    @pytest.mark.asyncio
    async def test_auto_rule_applies_category_and_description(self):
        service = _service(_statement([_row()]))
        service._repo.list_rules.return_value = [_rule()]
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        row = preview.rows[0]
        assert row.category_id == 10
        assert row.category_name == "Groceries"
        assert row.description == "Pingo Doce"
        assert row.suggestion_source == "rule_auto"
        assert row.needs_review is False
        assert row.review_reasons == []

    @pytest.mark.asyncio
    async def test_suggest_rule_flags_for_review(self):
        service = _service(_statement([_row()]))
        service._repo.list_rules.return_value = [_rule(mode="suggest")]
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].suggestion_source == "rule_suggest"
        assert preview.rows[0].needs_review is True
        assert preview.rows[0].review_reasons == ["rule_suggested"]
        assert preview.needs_review_count == 1

    @pytest.mark.asyncio
    async def test_transfer_rule_sets_type_and_counterpart(self):
        row = _row(raw_description="TRF P/ PoupeUp", amount=Decimal("-100.00"))
        service = _service(_statement([row]))
        service._repo.list_rules.return_value = [
            _rule(pattern="PoupeUp", description=None, merchant=None, category_id=None, transfer_account_id=5)
        ]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].type == "transfer"
        assert preview.rows[0].counterpart_account_id == 5
        assert preview.rows[0].needs_review is False
        assert preview.rows[0].review_reasons == []

    @pytest.mark.asyncio
    async def test_parser_flagged_row_needs_review_even_when_categorized(self):
        row = _row()
        row.flag_reason = "redated_installment"
        service = _service(_statement([row]))
        service._repo.list_rules.return_value = [_rule()]
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].category_id == 10
        assert preview.rows[0].suggestion_source == "rule_auto"
        assert preview.rows[0].needs_review is True
        assert preview.rows[0].review_reasons == ["redated_installment"]

    @pytest.mark.asyncio
    async def test_parser_flagged_row_combines_with_uncategorized_reason(self):
        row = _row()
        row.flag_reason = "redated_installment"
        service = _service(_statement([row]))

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].needs_review is True
        assert preview.rows[0].review_reasons == ["uncategorized", "redated_installment"]

    @pytest.mark.asyncio
    async def test_income_detected_from_positive_amount(self):
        row = _row(raw_description="TRANSFERENCIA - VENCIMENTO", amount=Decimal("3878.41"))
        service = _service(_statement([row]))

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].type == "income"

    @pytest.mark.asyncio
    async def test_knn_vote_applies_category(self):
        service = _service(_statement([_row()]))
        service._category_repo.list.return_value = [_category(10, "Groceries")]
        result = MagicMock(spec=EmbeddingSearchResult)
        result.source_id = 42
        result.similarity = 0.9
        service._embeddings.search.return_value = [result]
        neighbour = MagicMock()
        neighbour.id = 42
        neighbour.category_id = 10
        service._txn_repo.get_by_ids.return_value = [neighbour]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        row = preview.rows[0]
        assert row.category_id == 10
        assert row.suggestion_source == "knn"
        assert row.confidence == 1.0
        # Similarity-based matches are weaker evidence than an explicit rule or a
        # direct AI categorization, so they're flagged for review just like those --
        # previously they slipped through uncounted and unhighlighted in the UI.
        assert row.needs_review is True
        assert row.review_reasons == ["similarity_suggested"]

    @pytest.mark.asyncio
    async def test_knn_below_vote_threshold_leaves_uncategorized(self):
        service = _service(_statement([_row()]))
        service._category_repo.list.return_value = [
            _category(10, "Groceries"),
            _category(11, "Dining"),
        ]
        results = []
        for source_id, similarity in ((1, 0.8), (2, 0.8)):
            r = MagicMock(spec=EmbeddingSearchResult)
            r.source_id = source_id
            r.similarity = similarity
            results.append(r)
        service._embeddings.search.return_value = results
        n1, n2 = MagicMock(), MagicMock()
        n1.id, n1.category_id = 1, 10
        n2.id, n2.category_id = 2, 11
        service._txn_repo.get_by_ids.return_value = [n1, n2]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].category_id is None
        assert preview.rows[0].needs_review is True
        assert preview.rows[0].review_reasons == ["uncategorized"]

    @pytest.mark.asyncio
    async def test_llm_fallback_categorizes(self):
        llm = AsyncMock()
        llm.complete.return_value = LlmResponse(
            text='{"items": [{"index": 0, "category": "Groceries", "confidence": 0.8}]}',
            tokens_input=10,
            tokens_output=10,
        )
        service = _service(_statement([_row()]), llm=llm)
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        row = preview.rows[0]
        assert row.category_id == 10
        assert row.suggestion_source == "llm"
        assert row.confidence == 0.8
        assert row.needs_review is True
        assert row.review_reasons == ["ai_suggested"]

    @pytest.mark.asyncio
    async def test_llm_call_is_logged(self):
        llm = AsyncMock()
        llm.provider = "google"
        llm.model = "gemini-2.5-flash"
        llm.complete.return_value = LlmResponse(
            text='{"items": [{"index": 0, "category": "Groceries", "confidence": 0.8}]}',
            tokens_input=42,
            tokens_output=7,
            finish_reason="STOP",
        )
        service = _service(_statement([_row()]), llm=llm)
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        await service.preview(1, "x.csv", b"", provider="fakebank")

        service._session.add.assert_called_once()
        call = service._session.add.call_args[0][0]
        assert call.provider == "google"
        assert call.model == "gemini-2.5-flash"
        assert call.feature == "finance_import_categorization"
        assert call.tokens_input == 42
        assert call.tokens_output == 7
        assert call.finish_reason == "STOP"
        service._session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_llm_failure_does_not_log_a_call(self):
        llm = AsyncMock()
        llm.complete.side_effect = RuntimeError("boom")
        service = _service(_statement([_row()]), llm=llm)
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        await service.preview(1, "x.csv", b"", provider="fakebank")

        service._session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_unknown_category_ignored(self):
        llm = AsyncMock()
        llm.complete.return_value = LlmResponse(
            text='{"items": [{"index": 0, "category": "Made Up", "confidence": 0.9}]}',
            tokens_input=10,
            tokens_output=10,
        )
        service = _service(_statement([_row()]), llm=llm)
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].category_id is None

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_gracefully(self):
        llm = AsyncMock()
        llm.complete.side_effect = RuntimeError("boom")
        service = _service(_statement([_row()]), llm=llm)
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].category_id is None
        assert preview.new_count == 1


def _commit_row(**kwargs) -> ImportCommitRow:
    defaults = dict(
        date_posted=date(2026, 6, 1),
        bank_description="COMPRA 8597 PINGO DOCE CONTACTLESS",
        amount=Decimal("-23.17"),
        type="expense",
        deduplication_hash="hash-1",
        description="Pingo Doce",
        category_id=10,
    )
    defaults.update(kwargs)
    return ImportCommitRow(**defaults)


def _commit_request(rows: list[ImportCommitRow]) -> ImportCommitRequest:
    return ImportCommitRequest(
        account_id=1,
        provider="fakebank",
        source_file="x.csv",
        currency="EUR",
        closing_balance=Decimal("100.00"),
        rows=rows,
    )


class TestCommit:
    def _prepare(self, service: ImportService) -> None:
        batch = ImportBatch()
        batch.id = 7
        service._repo.add_batch.return_value = batch

        created = []

        async def _add(data):
            txn = MagicMock()
            txn.id = len(created) + 100
            txn.category_id = data.category_id
            txn.type = data.type
            txn.bank_description = data.bank_description
            txn.description = data.description
            txn.amount = data.amount
            created.append(data)
            return txn

        service._txn_repo.add.side_effect = _add
        service._created = created

    @pytest.mark.asyncio
    async def test_inserts_rows_and_skips_duplicates(self):
        service = _service()
        self._prepare(service)
        service._txn_repo.get_existing_dedup_hashes.return_value = {"hash-dup"}
        rows = [_commit_row(), _commit_row(deduplication_hash="hash-dup")]

        result = await service.commit(_commit_request(rows))

        assert result.batch_id == 7
        assert result.inserted == 1
        assert result.skipped_duplicates == 1
        assert len(service._created) == 1
        assert service._created[0].import_batch_id == 7
        assert service._created[0].source == "fakebank"

    @pytest.mark.asyncio
    async def test_duplicate_within_the_same_request_is_skipped_not_inserted_twice(self):
        # A hash repeating within request.rows (not yet in the DB) must be caught here --
        # otherwise the DB's unique constraint rejects the second insert and aborts the
        # whole batch instead of just skipping the one duplicate row.
        service = _service()
        self._prepare(service)
        service._txn_repo.get_existing_dedup_hashes.return_value = set()
        rows = [
            _commit_row(deduplication_hash="hash-repeat"),
            _commit_row(deduplication_hash="hash-repeat"),
            _commit_row(deduplication_hash="hash-unique"),
        ]

        result = await service.commit(_commit_request(rows))

        assert result.inserted == 2
        assert result.skipped_duplicates == 1
        assert len(service._created) == 2

    @pytest.mark.asyncio
    async def test_expense_amount_stored_positive(self):
        service = _service()
        self._prepare(service)

        await service.commit(_commit_request([_commit_row(amount=Decimal("-23.17"))]))

        assert service._created[0].amount == Decimal("23.17")
        assert service._created[0].type == "expense"

    @pytest.mark.asyncio
    async def test_transfer_amount_keeps_sign(self):
        service = _service()
        self._prepare(service)
        row = _commit_row(
            type="transfer",
            amount=Decimal("-100.00"),
            category_id=None,
            counterpart_account_id=5,
        )

        await service.commit(_commit_request([row]))

        assert service._created[0].amount == Decimal("-100.00")
        assert service._created[0].counterpart_account_id == 5

    @pytest.mark.asyncio
    async def test_save_rule_creates_rule(self):
        service = _service()
        self._prepare(service)
        row = _commit_row(
            save_rule=True,
            rule_pattern="PINGO DOCE",
            rule_mode="auto",
            rule_match_amount=False,
        )

        result = await service.commit(_commit_request([row]))

        assert result.rules_created == 1
        rule = service._repo.add_rule.call_args[0][0]
        assert rule.pattern == "PINGO DOCE"
        assert rule.category_id == 10
        assert rule.amount is None

    @pytest.mark.asyncio
    async def test_categorized_transactions_are_embedded(self):
        service = _service()
        self._prepare(service)

        await service.commit(
            _commit_request([_commit_row(), _commit_row(deduplication_hash="hash-2", category_id=None)])
        )

        service._embeddings.embed_many.assert_awaited_once()
        items = service._embeddings.embed_many.call_args[0][0]
        assert len(items) == 1
        assert items[0].source_type == "transaction"
        assert "Pingo Doce" in items[0].content


class TestStoredFile:
    @pytest.mark.asyncio
    async def test_preview_stores_original_file(self):
        files = AsyncMock()
        service = _service(_statement([_row()]), files=files)

        preview = await service.preview(1, "mov junho.csv", b"csv-bytes", provider="fakebank")

        files.save.assert_awaited_once()
        content, relative_path = files.save.call_args[0]
        assert content == b"csv-bytes"
        assert relative_path.startswith("fakebank/")
        assert relative_path.endswith("_mov_junho.csv")
        assert preview.stored_file == relative_path

    @pytest.mark.asyncio
    async def test_preview_without_storage_leaves_stored_file_empty(self):
        service = _service(_statement([_row()]))
        preview = await service.preview(1, "mov.csv", b"x", provider="fakebank")
        assert preview.stored_file is None

    @pytest.mark.asyncio
    async def test_preview_survives_storage_failure(self):
        files = AsyncMock()
        files.save.side_effect = OSError("disk full")
        service = _service(_statement([_row()]), files=files)

        preview = await service.preview(1, "mov.csv", b"x", provider="fakebank")

        assert preview.stored_file is None
        assert preview.new_count == 1

    @pytest.mark.asyncio
    async def test_commit_persists_stored_file_on_batch(self):
        service = _service()
        TestCommit()._prepare(service)
        request = _commit_request([_commit_row()])
        request.stored_file = "fakebank/abc_mov.csv"

        await service.commit(request)

        batch = service._repo.add_batch.call_args[0][0]
        assert batch.stored_file == "fakebank/abc_mov.csv"

    @pytest.mark.asyncio
    async def test_get_batch_file_returns_content_and_name(self):
        files = AsyncMock()
        files.read.return_value = b"csv-bytes"
        service = _service(files=files)
        batch = ImportBatch()
        batch.stored_file = "fakebank/abc_mov.csv"
        batch.source_file = "mov junho.csv"
        service._repo.get_batch.return_value = batch

        result = await service.get_batch_file(7)

        assert result == (b"csv-bytes", "mov junho.csv")
        files.read.assert_awaited_once_with("fakebank/abc_mov.csv")

    @pytest.mark.asyncio
    async def test_get_batch_file_none_when_not_stored(self):
        service = _service(files=AsyncMock())
        batch = ImportBatch()
        batch.stored_file = None
        service._repo.get_batch.return_value = batch

        assert await service.get_batch_file(7) is None


class TestDeleteBatch:
    @pytest.mark.asyncio
    async def test_missing_batch_returns_false(self):
        service = _service()
        service._repo.get_batch.return_value = None
        assert await service.delete_batch(99) is False

    @pytest.mark.asyncio
    async def test_deletes_transactions_embeddings_and_batch(self):
        service = _service()
        batch = ImportBatch()
        batch.stored_file = None
        service._repo.get_batch.return_value = batch
        service._txn_repo.get_ids_by_import_batch.return_value = [1, 2]
        service._txn_repo.delete_by_ids.return_value = 2

        assert await service.delete_batch(7) is True
        assert service._embeddings.delete_by_source.await_count == 2
        service._txn_repo.delete_by_ids.assert_awaited_once_with([1, 2])
        service._repo.delete_batch.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_deletes_stored_file_with_batch(self):
        files = AsyncMock()
        service = _service(files=files)
        batch = ImportBatch()
        batch.stored_file = "fakebank/abc_mov.csv"
        service._repo.get_batch.return_value = batch
        service._txn_repo.get_ids_by_import_batch.return_value = []
        service._txn_repo.delete_by_ids.return_value = 0

        assert await service.delete_batch(7) is True
        files.delete.assert_awaited_once_with("fakebank/abc_mov.csv")


class TestRulesManagement:
    @pytest.mark.asyncio
    async def test_list_rules_page_delegates_to_repo_with_filters(self):
        service = _service()
        service._repo.list_rules_page.return_value = [_rule(created_at=datetime(2026, 7, 20, 10, 0))]
        filters = ImportRuleFilters(pattern="PINGO")

        rules = await service.list_rules_page(filters)

        assert len(rules) == 1
        assert rules[0].pattern == "PINGO DOCE"
        service._repo.list_rules_page.assert_awaited_once_with(filters)

    @pytest.mark.asyncio
    async def test_update_rule_returns_updated_read_model(self):
        service = _service()
        service._repo.update_rule.return_value = _rule(
            pattern="PINGO DOCE UPDATED", created_at=datetime(2026, 7, 20, 10, 0)
        )

        result = await service.update_rule(1, ImportRuleUpdate(pattern="PINGO DOCE UPDATED"))

        assert result.pattern == "PINGO DOCE UPDATED"

    @pytest.mark.asyncio
    async def test_update_missing_rule_returns_none(self):
        service = _service()
        service._repo.update_rule.return_value = None

        assert await service.update_rule(99, ImportRuleUpdate(pattern="X")) is None

    @pytest.mark.asyncio
    async def test_reorder_reassigns_existing_slots_to_the_new_order(self):
        service = _service()
        rule_a = _rule(id=1, position=3, created_at=datetime(2026, 7, 20, 10, 0))
        rule_b = _rule(id=2, position=9, created_at=datetime(2026, 7, 20, 10, 0))
        rule_c = _rule(id=3, position=12, created_at=datetime(2026, 7, 20, 10, 0))
        service._repo.get_rules_by_ids.return_value = [rule_a, rule_b, rule_c]

        result = await service.reorder_rules([3, 1, 2])

        # Same three position slots (3, 9, 12), now handed out in the caller's order.
        assert rule_c.position == 3
        assert rule_a.position == 9
        assert rule_b.position == 12
        assert [r.id for r in result] == [3, 1, 2]
        service._repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reorder_ignores_ids_that_no_longer_exist(self):
        service = _service()
        rule_a = _rule(id=1, position=3, created_at=datetime(2026, 7, 20, 10, 0))
        service._repo.get_rules_by_ids.return_value = [rule_a]

        result = await service.reorder_rules([1, 999])

        assert [r.id for r in result] == [1]
        assert rule_a.position == 3

    @pytest.mark.asyncio
    async def test_reorder_empty_result_does_not_commit(self):
        service = _service()
        service._repo.get_rules_by_ids.return_value = []

        result = await service.reorder_rules([404])

        assert result == []
        service._repo.commit.assert_not_awaited()


class TestRulePositionAssignment:
    @pytest.mark.asyncio
    async def test_remembered_rules_get_sequential_positions(self):
        # Multiple "Remember this" rules saved from the same commit must not collide on
        # position -- each subsequent one should be appended after the last.
        service = _service()
        TestCommit()._prepare(service)
        service._repo.next_position.return_value = 7
        rows = [
            _commit_row(deduplication_hash="h1", save_rule=True, rule_pattern="A"),
            _commit_row(deduplication_hash="h2", save_rule=True, rule_pattern="B"),
        ]

        await service.commit(_commit_request(rows))

        added = [c.args[0] for c in service._repo.add_rule.call_args_list]
        assert [r.position for r in added] == [7, 8]

    @pytest.mark.asyncio
    async def test_grouped_remembered_rules_share_one_position_counter_across_currencies(self):
        service = _service()
        TestCommitGrouped()._prepare(service)
        service._repo.next_position.return_value = 3

        request = _grouped_commit_request(
            [
                _grouped_commit_row(currency="EUR", deduplication_hash="h1", save_rule=True, rule_pattern="A"),
                _grouped_commit_row(currency="PLN", deduplication_hash="h2", save_rule=True, rule_pattern="B"),
            ],
            account_map={"EUR": 1, "PLN": 2},
        )

        await service.commit_grouped(request)

        added = [c.args[0] for c in service._repo.add_rule.call_args_list]
        assert [r.position for r in added] == [3, 4]


class TestDetectCurrencies:
    @pytest.mark.asyncio
    async def test_unknown_provider_returns_none(self):
        service = _service()
        assert await service.detect_currencies("x.csv", b"", provider="nope") is None

    @pytest.mark.asyncio
    async def test_groups_by_currency_with_counts(self):
        rows = [
            _row(currency="EUR"), _row(currency="EUR"),
            _row(currency="PLN", balance_after=Decimal("10")),
        ]
        service = _service(_statement(rows))

        result = await service.detect_currencies("x.csv", b"", provider="fakebank")

        by_currency = {d.currency: d for d in result.currencies}
        assert by_currency["EUR"].row_count == 2
        assert by_currency["PLN"].row_count == 1

    @pytest.mark.asyncio
    async def test_auto_resolves_when_exactly_one_account_matches(self):
        service = _service(_statement([_row(currency="PLN")]))
        service._account_repo.list.return_value = [_account(5, "Revolut PLN", "PLN")]

        result = await service.detect_currencies("x.csv", b"", provider="fakebank")

        detection = result.currencies[0]
        assert detection.auto_account_id == 5
        assert [a.id for a in detection.candidate_accounts] == [5]

    @pytest.mark.asyncio
    async def test_no_auto_resolve_when_multiple_accounts_share_currency(self):
        service = _service(_statement([_row(currency="EUR")]))
        service._account_repo.list.return_value = [
            _account(1, "ActivoBank", "EUR"), _account(2, "PoupeUp", "EUR"),
        ]

        result = await service.detect_currencies("x.csv", b"", provider="fakebank")

        detection = result.currencies[0]
        assert detection.auto_account_id is None
        assert len(detection.candidate_accounts) == 2

    @pytest.mark.asyncio
    async def test_no_candidates_when_no_account_matches(self):
        service = _service(_statement([_row(currency="USD")]))
        service._account_repo.list.return_value = [_account(1, "ActivoBank", "EUR")]

        result = await service.detect_currencies("x.csv", b"", provider="fakebank")

        detection = result.currencies[0]
        assert detection.auto_account_id is None
        assert detection.candidate_accounts == []

    @pytest.mark.asyncio
    async def test_auto_resolves_by_provider_name_when_multiple_accounts_share_currency(self):
        service = _service(_statement([_row(currency="EUR")]))
        service._account_repo.list.return_value = [
            _account(1, "ActivoBank EUR", "EUR"), _account(2, "Fakebank EUR", "EUR"),
        ]

        result = await service.detect_currencies("x.csv", b"", provider="fakebank")

        detection = result.currencies[0]
        assert detection.auto_account_id == 2
        assert len(detection.candidate_accounts) == 2

    @pytest.mark.asyncio
    async def test_no_auto_resolve_when_provider_name_matches_multiple_accounts(self):
        service = _service(_statement([_row(currency="EUR")]))
        service._account_repo.list.return_value = [
            _account(1, "Fakebank EUR Main", "EUR"), _account(2, "Fakebank EUR Savings", "EUR"),
        ]

        result = await service.detect_currencies("x.csv", b"", provider="fakebank")

        detection = result.currencies[0]
        assert detection.auto_account_id is None


class TestPreviewGrouped:
    @pytest.mark.asyncio
    async def test_unknown_provider_returns_none(self):
        service = _service()
        assert await service.preview_grouped({}, "x.csv", b"", provider="nope") is None

    @pytest.mark.asyncio
    async def test_missing_account_map_entry_raises(self):
        service = _service(_statement([_row(currency="PLN")]))

        with pytest.raises(InvalidGroupedImportError):
            await service.preview_grouped({}, "x.csv", b"", provider="fakebank")

    @pytest.mark.asyncio
    async def test_groups_rows_by_currency(self):
        rows = [
            _row(currency="EUR", raw_description="A"),
            _row(currency="PLN", raw_description="B", balance_after=Decimal("10")),
        ]
        service = _service(_statement(rows))
        service._account_repo.list.return_value = [
            _account(1, "EUR Acc", "EUR"), _account(2, "PLN Acc", "PLN"),
        ]

        result = await service.preview_grouped(
            {"EUR": 1, "PLN": 2}, "x.csv", b"", provider="fakebank"
        )

        by_currency = {g.currency: g for g in result.groups}
        assert by_currency["EUR"].account_id == 1
        assert by_currency["EUR"].account_name == "EUR Acc"
        assert len(by_currency["EUR"].rows) == 1
        assert by_currency["PLN"].account_id == 2
        assert len(by_currency["PLN"].rows) == 1

    @pytest.mark.asyncio
    async def test_top_level_counts_sum_across_groups(self):
        rows = [_row(currency="EUR"), _row(currency="PLN", balance_after=Decimal("10"))]
        service = _service(_statement(rows))
        service._account_repo.list.return_value = [
            _account(1, "EUR Acc", "EUR"), _account(2, "PLN Acc", "PLN"),
        ]

        result = await service.preview_grouped(
            {"EUR": 1, "PLN": 2}, "x.csv", b"", provider="fakebank"
        )

        assert result.new_count == 2

    @pytest.mark.asyncio
    async def test_rules_applied_per_group(self):
        service = _service(_statement([_row(currency="EUR")]))
        service._account_repo.list.return_value = [_account(1, "EUR Acc", "EUR")]
        service._repo.list_rules.return_value = [_rule()]
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        result = await service.preview_grouped({"EUR": 1}, "x.csv", b"", provider="fakebank")

        row = result.groups[0].rows[0]
        assert row.category_id == 10
        assert row.suggestion_source == "rule_auto"

    @pytest.mark.asyncio
    async def test_duplicate_marked_per_group(self):
        row = _row(currency="EUR")
        service = _service(_statement([row]))
        service._account_repo.list.return_value = [_account(1, "EUR Acc", "EUR")]
        dup_hash = _compute_dedup_hash(1, row, 1)
        service._txn_repo.get_existing_dedup_hashes.return_value = {dup_hash}

        result = await service.preview_grouped({"EUR": 1}, "x.csv", b"", provider="fakebank")

        assert result.groups[0].rows[0].status == "duplicate"
        assert result.duplicate_count == 1
        assert result.new_count == 0


def _grouped_commit_row(**kwargs) -> ImportCommitGroupedRow:
    defaults = dict(
        date_posted=date(2026, 6, 1),
        bank_description="Some desc",
        amount=Decimal("-10.00"),
        type="expense",
        currency="EUR",
        deduplication_hash="hash-1",
        category_id=10,
    )
    defaults.update(kwargs)
    return ImportCommitGroupedRow(**defaults)


def _grouped_commit_request(rows, account_map=None) -> ImportCommitGroupedRequest:
    return ImportCommitGroupedRequest(
        provider="fakebank",
        source_file="x.csv",
        account_map=account_map if account_map is not None else {"EUR": 1},
        rows=rows,
    )


class TestCommitGrouped:
    def _prepare(self, service: ImportService):
        batches: list = []

        async def _add_batch(batch):
            batch.id = len(batches) + 1
            batches.append(batch)
            return batch
        service._repo.add_batch.side_effect = _add_batch

        created: list = []

        async def _add_txn(data):
            txn = MagicMock()
            txn.id = len(created) + 100
            txn.category_id = data.category_id
            txn.type = data.type
            txn.bank_description = data.bank_description
            txn.description = data.description
            created.append(data)
            return txn
        service._txn_repo.add.side_effect = _add_txn
        service._repo.add_rule = MagicMock()
        service._account_repo.get.return_value = MagicMock()
        return created, batches

    @pytest.mark.asyncio
    async def test_missing_account_map_entry_raises(self):
        service = _service()
        request = _grouped_commit_request([_grouped_commit_row()], account_map={})

        with pytest.raises(InvalidGroupedImportError):
            await service.commit_grouped(request)

    @pytest.mark.asyncio
    async def test_missing_account_raises(self):
        service = _service()
        service._account_repo.get.return_value = None
        request = _grouped_commit_request([_grouped_commit_row()], account_map={"EUR": 999})

        with pytest.raises(InvalidGroupedImportError):
            await service.commit_grouped(request)

    @pytest.mark.asyncio
    async def test_creates_one_batch_per_currency(self):
        service = _service()
        created, batches = self._prepare(service)

        request = _grouped_commit_request(
            [
                _grouped_commit_row(currency="EUR", deduplication_hash="h1"),
                _grouped_commit_row(currency="PLN", deduplication_hash="h2"),
            ],
            account_map={"EUR": 1, "PLN": 2},
        )

        result = await service.commit_grouped(request)

        assert len(batches) == 2
        assert len(result.batches) == 2
        assert result.total_inserted == 2
        currencies = {b.currency: b for b in result.batches}
        assert currencies["EUR"].account_id == 1
        assert currencies["PLN"].account_id == 2

    @pytest.mark.asyncio
    async def test_skips_duplicates_per_row(self):
        service = _service()
        self._prepare(service)
        service._txn_repo.get_existing_dedup_hashes.return_value = {"h1"}

        request = _grouped_commit_request(
            [
                _grouped_commit_row(currency="EUR", deduplication_hash="h1"),
                _grouped_commit_row(currency="EUR", deduplication_hash="h2"),
            ],
            account_map={"EUR": 1},
        )

        result = await service.commit_grouped(request)

        assert result.total_inserted == 1
        assert result.total_skipped_duplicates == 1

    @pytest.mark.asyncio
    async def test_duplicate_within_the_same_request_is_skipped_not_inserted_twice(self):
        service = _service()
        self._prepare(service)
        service._txn_repo.get_existing_dedup_hashes.return_value = set()

        request = _grouped_commit_request(
            [
                _grouped_commit_row(currency="EUR", deduplication_hash="hash-repeat"),
                _grouped_commit_row(currency="EUR", deduplication_hash="hash-repeat"),
            ],
            account_map={"EUR": 1},
        )

        result = await service.commit_grouped(request)

        assert result.total_inserted == 1
        assert result.total_skipped_duplicates == 1

    @pytest.mark.asyncio
    async def test_transfer_amount_keeps_sign(self):
        service = _service()
        created, _ = self._prepare(service)

        request = _grouped_commit_request(
            [_grouped_commit_row(currency="EUR", type="transfer", amount=Decimal("-100.00"), category_id=None)],
            account_map={"EUR": 1},
        )

        await service.commit_grouped(request)

        assert created[0].amount == Decimal("-100.00")

    @pytest.mark.asyncio
    async def test_expense_amount_stored_positive(self):
        service = _service()
        created, _ = self._prepare(service)

        request = _grouped_commit_request(
            [_grouped_commit_row(currency="EUR", type="expense", amount=Decimal("-23.17"))],
            account_map={"EUR": 1},
        )

        await service.commit_grouped(request)

        assert created[0].amount == Decimal("23.17")

    @pytest.mark.asyncio
    async def test_save_rule_creates_rule(self):
        service = _service()
        self._prepare(service)

        request = _grouped_commit_request(
            [_grouped_commit_row(currency="EUR", save_rule=True, rule_pattern="PINGO DOCE")],
            account_map={"EUR": 1},
        )

        result = await service.commit_grouped(request)

        assert result.rules_created == 1

    @pytest.mark.asyncio
    async def test_categorized_transactions_are_embedded(self):
        service = _service()
        self._prepare(service)

        request = _grouped_commit_request(
            [_grouped_commit_row(currency="EUR", category_id=10)], account_map={"EUR": 1}
        )

        await service.commit_grouped(request)

        service._embeddings.embed_many.assert_awaited_once()
        assert len(service._embeddings.embed_many.call_args[0][0]) == 1
