import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.features.core.embeddings.schemas import EmbeddingSearchResult
from app.features.finance.imports.schemas import (
    ImportCommitRequest,
    ImportCommitRow,
)
from app.features.finance.imports.service import (
    ImportService,
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
    service._repo.list_rules.return_value = []
    service._repo.add_rule = MagicMock()
    service._txn_repo.get_existing_dedup_hashes.return_value = set()
    service._category_repo.list.return_value = []
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
        assert preview.rows[1].status == "new"

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

    @pytest.mark.asyncio
    async def test_suggest_rule_flags_for_review(self):
        service = _service(_statement([_row()]))
        service._repo.list_rules.return_value = [_rule(mode="suggest")]
        service._category_repo.list.return_value = [_category(10, "Groceries")]

        preview = await service.preview(1, "x.csv", b"", provider="fakebank")

        assert preview.rows[0].suggestion_source == "rule_suggest"
        assert preview.rows[0].needs_review is True
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
        assert row.needs_review is False

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

        assert service._embeddings.embed.await_count == 1
        embedded = service._embeddings.embed.call_args[0][0]
        assert embedded.source_type == "transaction"
        assert "Pingo Doce" in embedded.content


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
