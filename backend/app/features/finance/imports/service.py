import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.schemas import EmbeddingCreate, EmbeddingSearchRequest
from app.features.core.embeddings.service import EmbeddingService
from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import AccountFilters
from app.features.finance.accounts.tables import Account
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.imports.prompts import CATEGORIZE_SYSTEM_PROMPT, CATEGORIZE_USER_PROMPT
from app.features.finance.imports.repository import ImportRepository
from app.features.finance.imports.schemas import (
    CurrencyCandidateAccount,
    CurrencyDetection,
    DetectCurrenciesResponse,
    ImportBatchRead,
    ImportCommitBatchResult,
    ImportCommitGroupedRequest,
    ImportCommitGroupedResponse,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportCurrencyGroup,
    ImportPreviewGroupedResponse,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportRuleCreate,
    ImportRuleFilters,
    ImportRuleRead,
    ImportRuleUpdate,
)
from app.features.finance.imports.tables import ImportBatch, ImportRule
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import TransactionCreate
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import FileStorage
from app.shared.llm import LlmProvider
from app.shared.statement import ParsedRow, StatementParser

logger = logging.getLogger(__name__)

TRANSACTION_SOURCE_TYPE = "transaction"
LLM_CALL_FEATURE = "finance_import_categorization"

# Providers that can mix several currencies in one export and therefore go through the
# grouped (multi-account) preview/commit flow instead of the single-account one.
GROUPED_PROVIDERS = frozenset({"revolut", "wise"})

_KNN_LIMIT = 7
# Cosine similarity thresholds (0..1). Raised from 0.55/0.6 -- the lower values were
# letting semantically-unrelated past transactions vote on a category often enough to
# feel like noise; both gates are now stricter so a kNN suggestion only fires when the
# match is genuinely close.
_KNN_THRESHOLD = 0.72
_KNN_MIN_VOTE = 0.7

_NOISE_PATTERNS = [
    re.compile(r"^COMPRA \d+\s+"),
    re.compile(r"^LEV ATM \d+\s+"),
    re.compile(r"^PAG BXVAL-\s*\d+\s+"),
    re.compile(r"^PAGSERV\s+"),
    re.compile(r"^TRF MB WAY P/\s*"),
    re.compile(r"^TRF\.? (P/|DE)\s*"),
    re.compile(r"^DD\s+"),
    re.compile(r"\bCONTACTLESS\b"),
    re.compile(r"\b\d{4}-\d{3}\b"),
    re.compile(r"\(Parcela \d+ de \d+\)", re.IGNORECASE),
    re.compile(r"-?\s*Parcela \d+/\d+", re.IGNORECASE),
]
_WHITESPACE = re.compile(r"\s+")


def _clean_description(raw: str) -> str:
    text = raw.strip()
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def _compute_dedup_hash(account_id: int, row: ParsedRow, occurrence: int) -> str:
    # balance_after alone isn't always a reliable disambiguator: two distinct same-day,
    # same-amount, same-description rows can still coincidentally leave the same running
    # balance (e.g. two top-ups on the same day, each immediately spent back down to zero
    # by an unrelated transaction in between). row.posted_at folds in intra-day precision
    # for providers that have it (Revolut, Wise) to break that tie without touching the
    # date-only date_posted used everywhere else.
    disambiguator = (
        str(row.balance_after) if row.balance_after is not None else f"occ:{occurrence}"
    )
    payload = "|".join(
        [
            str(account_id),
            row.date_posted.isoformat(),
            row.date_value.isoformat(),
            row.raw_description,
            str(row.amount),
            disambiguator,
            row.posted_at or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rule_matches(rule: ImportRule, raw_description: str, amount: Decimal) -> bool:
    if rule.pattern.lower() not in raw_description.lower():
        return False
    if rule.amount is not None and rule.amount != amount:
        return False
    return True


def _auto_match_account(matching: list[Account], provider: str) -> int | None:
    """Pick the account to pre-select for a detected currency. A single currency match
    is unambiguous; with several (e.g. an ActivoBank EUR account alongside a Revolut EUR
    account), narrow by provider name (e.g. "Revolut EUR") before giving up and leaving
    it to the user."""
    if len(matching) == 1:
        return matching[0].id
    if len(matching) > 1:
        provider_matches = [a for a in matching if provider.lower() in a.name.lower()]
        if len(provider_matches) == 1:
            return provider_matches[0].id
    return None


class InvalidGroupedImportError(Exception):
    """Raised when a grouped (multi-currency) import request is malformed: an unknown
    provider, or an account_map that doesn't cover every currency present."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _extract_json(text: str) -> dict | None:
    """Extract the first JSON object from an LLM response, tolerating code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


class ImportService:

    def __init__(
        self,
        session: AsyncSession,
        parsers: dict[str, StatementParser],
        embedding_service: EmbeddingService,
        llm_provider: LlmProvider | None = None,
        file_storage: FileStorage | None = None,
    ) -> None:
        self._session = session
        self._repo = ImportRepository(session)
        self._txn_repo = TransactionRepository(session)
        self._category_repo = CategoryRepository(session)
        self._account_repo = AccountRepository(session)
        self._parsers = parsers
        self._embeddings = embedding_service
        self._llm = llm_provider
        self._files = file_storage

    # -- preview ---------------------------------------------------------

    async def preview(
        self,
        account_id: int,
        filename: str,
        content: bytes,
        provider: str | None = None,
    ) -> ImportPreviewResponse | None:
        parser = self._resolve_parser(provider, filename, content)
        if parser is None:
            logger.warning("Import preview: no parser found for file=%r provider=%r", filename, provider)
            return None
        if parser.provider in GROUPED_PROVIDERS:
            logger.warning(
                "Import preview: provider=%s requires the grouped multi-currency flow", parser.provider
            )
            return None

        try:
            statement = parser.parse(content)
        except Exception as exc:
            logger.error("Import preview: parse failed provider=%s file=%r error=%s", parser.provider, filename, exc)
            return None
        logger.info(
            "Import preview: provider=%s file=%r rows=%d account_id=%d",
            parser.provider, filename, len(statement.rows), account_id,
        )

        stored_file = await self._store_file(parser.provider, filename, content)
        rows = self._build_rows(account_id, statement.rows)
        await self._mark_duplicates(rows)
        rules = await self._repo.list_rules()
        categories = {c.id: c.name for c in await self._category_repo.list()}
        self._apply_rules(rows, rules, categories)
        await self._apply_knn(rows, categories)
        await self._apply_llm(rows, categories)

        self._apply_review_reasons(rows, statement.rows)

        return ImportPreviewResponse(
            provider=parser.provider,
            account_id=account_id,
            source_file=filename,
            stored_file=stored_file,
            currency=statement.currency,
            account_number=statement.account_number,
            period_start=statement.period_start,
            period_end=statement.period_end,
            closing_balance=statement.closing_balance,
            rows=rows,
            new_count=sum(1 for r in rows if r.status == "new"),
            duplicate_count=sum(1 for r in rows if r.status == "duplicate"),
            needs_review_count=sum(1 for r in rows if r.needs_review),
        )

    def _apply_review_reasons(
        self, rows: list[ImportPreviewRow], parsed: list[ParsedRow]
    ) -> None:
        for row in rows:
            if row.status != "new" or row.type == "transfer":
                continue
            reasons: list[str] = []
            if row.category_id is None:
                reasons.append("uncategorized")
            elif row.suggestion_source == "rule_suggest":
                reasons.append("rule_suggested")
            elif row.suggestion_source == "llm":
                reasons.append("ai_suggested")
            elif row.suggestion_source == "knn":
                reasons.append("similarity_suggested")
            row.review_reasons = reasons
            row.needs_review = bool(reasons)
        for preview_row, parsed_row in zip(rows, parsed):
            if parsed_row.flag_reason and preview_row.status == "new":
                if parsed_row.flag_reason not in preview_row.review_reasons:
                    preview_row.review_reasons.append(parsed_row.flag_reason)
                preview_row.needs_review = True

    async def _store_file(self, provider: str, filename: str, content: bytes) -> str | None:
        """Persist the original upload; the content-hash path makes re-uploads idempotent."""
        if self._files is None:
            return None
        digest = hashlib.sha256(content).hexdigest()[:16]
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[-100:]
        relative_path = f"{provider}/{digest}_{safe_name}"
        try:
            await self._files.save(content, relative_path)
        except Exception as exc:
            logger.error("Statement file save failed: path=%s error=%s", relative_path, exc)
            return None
        return relative_path

    def _resolve_parser(
        self, provider: str | None, filename: str, content: bytes
    ) -> StatementParser | None:
        if provider:
            return self._parsers.get(provider)
        for parser in self._parsers.values():
            if parser.can_parse(filename, content):
                return parser
        return None

    def _build_rows(self, account_id: int, parsed: list[ParsedRow]) -> list[ImportPreviewRow]:
        occurrences: dict[tuple, int] = defaultdict(int)
        rows: list[ImportPreviewRow] = []
        for parsed_row in parsed:
            key = (parsed_row.date_posted, parsed_row.raw_description, parsed_row.amount)
            occurrences[key] += 1
            rows.append(
                ImportPreviewRow(
                    date_posted=parsed_row.date_posted,
                    date_value=parsed_row.date_value,
                    bank_description=parsed_row.raw_description,
                    amount=parsed_row.amount,
                    balance_after=parsed_row.balance_after,
                    type=parsed_row.suggested_type or ("expense" if parsed_row.amount < 0 else "income"),
                    status="new",
                    deduplication_hash=_compute_dedup_hash(
                        account_id, parsed_row, occurrences[key]
                    ),
                )
            )
        return rows

    async def _mark_duplicates(self, rows: list[ImportPreviewRow]) -> None:
        """Flag rows already present in the DB, as well as rows that repeat within this
        same file (e.g. overlapping export date ranges) -- both would otherwise slip
        through preview as "new" and then get silently dropped at commit time, leaving
        the user unable to tell why fewer rows landed than they saw on screen."""
        existing = await self._txn_repo.get_existing_dedup_hashes(
            [r.deduplication_hash for r in rows]
        )
        seen: set[str] = set()
        for row in rows:
            if row.deduplication_hash in existing:
                row.status = "duplicate"
                row.duplicate_reason = "already_imported"
            elif row.deduplication_hash in seen:
                row.status = "duplicate"
                row.duplicate_reason = "repeated_in_file"
            else:
                seen.add(row.deduplication_hash)

    def _apply_rules(
        self,
        rows: list[ImportPreviewRow],
        rules: list[ImportRule],
        categories: dict[int, str],
    ) -> None:
        for row in rows:
            if row.status != "new":
                continue
            for rule in rules:
                if not _rule_matches(rule, row.bank_description, row.amount):
                    continue
                if rule.transfer_account_id is not None:
                    row.type = "transfer"
                    row.counterpart_account_id = rule.transfer_account_id
                row.description = rule.description or row.description
                row.merchant = rule.merchant or row.merchant
                if rule.category_id is not None:
                    row.category_id = rule.category_id
                    row.category_name = categories.get(rule.category_id)
                row.suggestion_source = "rule_auto" if rule.mode == "auto" else "rule_suggest"
                break

    async def _apply_knn(
        self, rows: list[ImportPreviewRow], categories: dict[int, str]
    ) -> None:
        for row in rows:
            if row.status != "new" or row.type == "transfer":
                continue
            if row.category_id is not None or row.suggestion_source is not None:
                continue
            cleaned = _clean_description(row.bank_description)
            if not cleaned:
                continue
            try:
                results = await self._embeddings.search(
                    EmbeddingSearchRequest(
                        query=cleaned,
                        source_types=[TRANSACTION_SOURCE_TYPE],
                        limit=_KNN_LIMIT,
                        threshold=_KNN_THRESHOLD,
                    )
                )
            except Exception as exc:
                logger.error("Import kNN search failed: error=%s", exc)
                return
            if not results:
                continue
            neighbours = await self._txn_repo.get_by_ids([r.source_id for r in results])
            similarity_by_id = {r.source_id: r.similarity for r in results}
            votes: dict[int, float] = defaultdict(float)
            total = 0.0
            for txn in neighbours:
                weight = similarity_by_id.get(txn.id, 0.0)
                total += weight
                if txn.category_id is not None:
                    votes[txn.category_id] += weight
            if not votes or total == 0:
                continue
            best_category, best_weight = max(votes.items(), key=lambda item: item[1])
            confidence = best_weight / total
            if confidence >= _KNN_MIN_VOTE:
                row.category_id = best_category
                row.category_name = categories.get(best_category)
                row.suggestion_source = "knn"
                row.confidence = round(confidence, 2)

    async def _apply_llm(
        self, rows: list[ImportPreviewRow], categories: dict[int, str]
    ) -> None:
        if self._llm is None or not categories:
            return
        pending = [
            r for r in rows
            if r.status == "new" and r.type != "transfer" and r.category_id is None
        ]
        if not pending:
            return

        listing = "\n".join(
            f"{i}. {_clean_description(r.bank_description)} ({r.amount})"
            for i, r in enumerate(pending)
        )
        prompt = CATEGORIZE_USER_PROMPT.format(
            categories="\n".join(f"- {name}" for name in categories.values()),
            transactions=listing,
        )
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        try:
            response = await self._llm.complete(messages=messages, system=CATEGORIZE_SYSTEM_PROMPT)
        except Exception as exc:
            logger.error("Import LLM categorization failed: error=%s", exc)
            return
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm.provider,
            model=self._llm.model,
            feature=LLM_CALL_FEATURE,
            prompt=messages,
            response=response.text,
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            latency_ms=latency_ms,
            finish_reason=response.finish_reason,
        )
        await self._session.commit()

        payload = _extract_json(response.text)
        if payload is None or not isinstance(payload.get("items"), list):
            logger.warning("Import LLM categorization: unparseable response")
            return

        names_to_ids = {name.lower(): cid for cid, name in categories.items()}
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            category = item.get("category")
            if not isinstance(index, int) or index < 0 or index >= len(pending):
                continue
            if not isinstance(category, str):
                continue
            category_id = names_to_ids.get(category.lower())
            if category_id is None:
                continue
            row = pending[index]
            row.category_id = category_id
            row.category_name = categories[category_id]
            row.suggestion_source = "llm"
            confidence = item.get("confidence")
            if isinstance(confidence, (int, float)):
                row.confidence = round(float(confidence), 2)
        logger.debug("Import LLM categorization: candidates=%d", len(pending))

    # -- commit ----------------------------------------------------------

    async def commit(self, request: ImportCommitRequest) -> ImportCommitResponse:
        existing = await self._txn_repo.get_existing_dedup_hashes(
            [r.deduplication_hash for r in request.rows]
        )
        # A hash can also repeat WITHIN this request (e.g. overlapping export date
        # ranges produce the same source line twice); the DB's unique constraint would
        # reject the second one and abort the whole batch insert if it weren't caught here.
        seen: set[str] = set()
        to_insert = []
        for row in request.rows:
            if row.deduplication_hash in existing or row.deduplication_hash in seen:
                continue
            seen.add(row.deduplication_hash)
            to_insert.append(row)
        skipped = len(request.rows) - len(to_insert)

        batch = await self._repo.add_batch(
            ImportBatch(
                account_id=request.account_id,
                provider=request.provider,
                source_file=request.source_file,
                stored_file=request.stored_file,
                period_start=request.period_start,
                period_end=request.period_end,
                closing_balance=request.closing_balance,
                inserted_count=len(to_insert),
                duplicate_count=skipped,
            )
        )

        transactions = []
        for row in to_insert:
            transactions.append(
                await self._txn_repo.add(
                    TransactionCreate(
                        account_id=request.account_id,
                        date=datetime.combine(row.date_posted, datetime.min.time()),
                        amount=row.amount if row.type == "transfer" else abs(row.amount),
                        currency=request.currency,
                        type=row.type,
                        category_id=row.category_id,
                        description=row.description,
                        bank_description=row.bank_description,
                        note=row.note,
                        merchant=row.merchant,
                        source=request.provider,
                        counterpart_account_id=row.counterpart_account_id,
                        deduplication_hash=row.deduplication_hash,
                        import_batch_id=batch.id,
                    )
                )
            )

        rules_created = 0
        next_position = await self._repo.next_position()
        for row in to_insert:
            if not row.save_rule or not row.rule_pattern:
                continue
            self._repo.add_rule(
                ImportRule(
                    pattern=row.rule_pattern,
                    amount=row.amount if row.rule_match_amount else None,
                    mode=row.rule_mode,
                    description=row.description,
                    merchant=row.merchant,
                    category_id=row.category_id,
                    transfer_account_id=row.counterpart_account_id if row.type == "transfer" else None,
                    position=next_position,
                )
            )
            next_position += 1
            rules_created += 1

        await self._repo.commit()
        logger.info(
            "Import committed: batch_id=%d account_id=%d inserted=%d skipped=%d rules=%d",
            batch.id, request.account_id, len(transactions), skipped, rules_created,
        )

        await self._embed_transactions(transactions)

        return ImportCommitResponse(
            batch_id=batch.id,
            inserted=len(transactions),
            skipped_duplicates=skipped,
            rules_created=rules_created,
        )

    async def _embed_transactions(self, transactions: list) -> None:
        """Index categorized imported transactions so future imports can kNN-vote on them."""
        items = []
        for txn in transactions:
            if txn.category_id is None or txn.type == "transfer":
                continue
            content = _clean_description(txn.bank_description or "")
            if txn.description:
                content = f"{txn.description} | {content}" if content else txn.description
            if not content:
                continue
            items.append(
                EmbeddingCreate(source_type=TRANSACTION_SOURCE_TYPE, source_id=txn.id, content=content)
            )
        if items:
            await self._embeddings.embed_many(items)

    # -- batches and rules ----------------------------------------------

    async def list_batches(self) -> list[ImportBatchRead]:
        batches = await self._repo.list_batches()
        return [ImportBatchRead.model_validate(b) for b in batches]

    async def delete_batch(self, batch_id: int) -> bool:
        batch = await self._repo.get_batch(batch_id)
        if batch is None:
            logger.debug("Import batch delete: id=%d not found", batch_id)
            return False
        transaction_ids = await self._txn_repo.get_ids_by_import_batch(batch_id)
        for transaction_id in transaction_ids:
            await self._embeddings.delete_by_source(TRANSACTION_SOURCE_TYPE, transaction_id)
        deleted = await self._txn_repo.delete_by_ids(transaction_ids)
        if batch.stored_file and self._files is not None:
            try:
                await self._files.delete(batch.stored_file)
            except Exception as exc:
                logger.error("Statement file delete failed: path=%s error=%s", batch.stored_file, exc)
        await self._repo.delete_batch(batch_id)
        logger.info("Import batch deleted: id=%d transactions=%d", batch_id, deleted)
        return True

    async def get_batch_file(self, batch_id: int) -> tuple[bytes, str] | None:
        """Return the original statement file bytes and its display name, if stored."""
        batch = await self._repo.get_batch(batch_id)
        if batch is None or not batch.stored_file or self._files is None:
            return None
        content = await self._files.read(batch.stored_file)
        if content is None:
            return None
        return content, batch.source_file or batch.stored_file.rsplit("/", 1)[-1]

    async def list_rules(self) -> list[ImportRuleRead]:
        rules = await self._repo.list_rules()
        return [ImportRuleRead.model_validate(r) for r in rules]

    async def list_rules_page(self, filters: ImportRuleFilters) -> list[ImportRuleRead]:
        rules = await self._repo.list_rules_page(filters)
        return [ImportRuleRead.model_validate(r) for r in rules]

    async def create_rule(self, data: ImportRuleCreate) -> ImportRuleRead:
        rule = await self._repo.create_rule(data)
        logger.info("Import rule created: id=%d pattern=%r mode=%s", rule.id, rule.pattern, rule.mode)
        return ImportRuleRead.model_validate(rule)

    async def update_rule(self, rule_id: int, data: ImportRuleUpdate) -> ImportRuleRead | None:
        rule = await self._repo.update_rule(rule_id, data)
        if rule is None:
            logger.debug("Import rule update: id=%d not found", rule_id)
            return None
        logger.info(
            "Import rule updated: id=%d fields=%s", rule_id, list(data.model_dump(exclude_unset=True).keys())
        )
        return ImportRuleRead.model_validate(rule)

    async def reorder_rules(self, rule_ids: list[int]) -> list[ImportRuleRead]:
        """Apply a client-defined order to a set of rules in one shot: the rules keep the
        same block of position "slots" they already occupy, those slots are just handed
        out to the rules in the caller's new order -- rules outside this set, and any
        gaps from deleted rules, are left untouched."""
        rules = await self._repo.get_rules_by_ids(rule_ids)
        by_id = {r.id: r for r in rules}
        ordered = [by_id[rid] for rid in rule_ids if rid in by_id]
        slots = sorted(r.position for r in ordered)
        for rule, position in zip(ordered, slots):
            rule.position = position
        if ordered:
            await self._repo.commit()
            logger.info("Import rules reordered: ids=%s", [r.id for r in ordered])
        return [ImportRuleRead.model_validate(r) for r in ordered]

    async def delete_rule(self, rule_id: int) -> bool:
        deleted = await self._repo.delete_rule(rule_id)
        if deleted:
            logger.info("Import rule deleted: id=%d", rule_id)
        return deleted

    def available_providers(self) -> list[str]:
        """Single-account providers only; grouped (multi-currency) providers are offered
        through a separate upload flow (detect_currencies / preview_grouped / commit_grouped)."""
        return sorted(k for k in self._parsers if k not in GROUPED_PROVIDERS)

    def available_grouped_providers(self) -> list[str]:
        return sorted(k for k in self._parsers if k in GROUPED_PROVIDERS)

    # -- grouped (multi-currency) preview/commit --------------------------

    async def detect_currencies(
        self, filename: str, content: bytes, provider: str
    ) -> DetectCurrenciesResponse | None:
        parser = self._parsers.get(provider)
        if parser is None:
            logger.warning("Currency detection: unknown provider=%r", provider)
            return None
        try:
            statement = parser.parse(content)
        except Exception as exc:
            logger.error(
                "Currency detection: parse failed provider=%s file=%r error=%s", provider, filename, exc
            )
            return None

        counts: dict[str, int] = defaultdict(int)
        for row in statement.rows:
            counts[row.currency] += 1

        all_accounts = await self._account_repo.list(AccountFilters())
        detections = []
        for currency in sorted(counts):
            matching = [a for a in all_accounts if a.currency == currency]
            detections.append(
                CurrencyDetection(
                    currency=currency,
                    row_count=counts[currency],
                    auto_account_id=_auto_match_account(matching, provider),
                    candidate_accounts=[
                        CurrencyCandidateAccount(id=a.id, name=a.name) for a in matching
                    ],
                )
            )
        logger.info(
            "Currency detection: provider=%s file=%r currencies=%s",
            parser.provider, filename, sorted(counts),
        )
        return DetectCurrenciesResponse(provider=parser.provider, currencies=detections)

    async def preview_grouped(
        self,
        account_map: dict[str, int],
        filename: str,
        content: bytes,
        provider: str,
    ) -> ImportPreviewGroupedResponse | None:
        parser = self._parsers.get(provider)
        if parser is None:
            logger.warning("Grouped import preview: unknown provider=%r", provider)
            return None
        try:
            statement = parser.parse(content)
        except Exception as exc:
            logger.error(
                "Grouped import preview: parse failed provider=%s file=%r error=%s", provider, filename, exc
            )
            return None

        by_currency: dict[str, list[ParsedRow]] = defaultdict(list)
        for row in statement.rows:
            by_currency[row.currency].append(row)

        missing = sorted(c for c in by_currency if c not in account_map)
        if missing:
            raise InvalidGroupedImportError(
                f"No account selected for currency(ies): {', '.join(missing)}"
            )

        stored_file = await self._store_file(parser.provider, filename, content)
        rules = await self._repo.list_rules()
        categories = {c.id: c.name for c in await self._category_repo.list()}
        accounts_by_id = {a.id: a.name for a in await self._account_repo.list(AccountFilters())}

        groups: list[ImportCurrencyGroup] = []
        for currency in sorted(by_currency):
            parsed_rows = by_currency[currency]
            account_id = account_map[currency]
            rows = self._build_rows(account_id, parsed_rows)
            await self._mark_duplicates(rows)
            self._apply_rules(rows, rules, categories)
            await self._apply_knn(rows, categories)
            await self._apply_llm(rows, categories)
            self._apply_review_reasons(rows, parsed_rows)

            dates = [r.date_posted for r in parsed_rows]
            groups.append(
                ImportCurrencyGroup(
                    currency=currency,
                    account_id=account_id,
                    account_name=accounts_by_id.get(account_id, "?"),
                    period_start=min(dates) if dates else None,
                    period_end=max(dates) if dates else None,
                    closing_balance=parsed_rows[-1].balance_after if parsed_rows else None,
                    rows=rows,
                    new_count=sum(1 for r in rows if r.status == "new"),
                    duplicate_count=sum(1 for r in rows if r.status == "duplicate"),
                    needs_review_count=sum(1 for r in rows if r.needs_review),
                )
            )

        logger.info(
            "Grouped import preview: provider=%s file=%r currencies=%s",
            parser.provider, filename, sorted(by_currency),
        )
        return ImportPreviewGroupedResponse(
            provider=parser.provider,
            source_file=filename,
            stored_file=stored_file,
            groups=groups,
            new_count=sum(g.new_count for g in groups),
            duplicate_count=sum(g.duplicate_count for g in groups),
            needs_review_count=sum(g.needs_review_count for g in groups),
        )

    async def commit_grouped(self, request: ImportCommitGroupedRequest) -> ImportCommitGroupedResponse:
        by_currency: dict[str, list] = defaultdict(list)
        for row in request.rows:
            by_currency[row.currency].append(row)

        missing = sorted(c for c in by_currency if c not in request.account_map)
        if missing:
            raise InvalidGroupedImportError(
                f"No account selected for currency(ies): {', '.join(missing)}"
            )
        for currency, account_id in request.account_map.items():
            if await self._account_repo.get(account_id) is None:
                raise InvalidGroupedImportError(f"Account for currency {currency} not found")

        existing = await self._txn_repo.get_existing_dedup_hashes(
            [r.deduplication_hash for r in request.rows]
        )
        # See commit(): a hash can also repeat WITHIN this request, which the
        # existing-in-DB check alone wouldn't catch and would abort the batch insert.
        seen: set[str] = set()

        batch_results: list[ImportCommitBatchResult] = []
        all_transactions = []
        total_rules_created = 0
        next_position = await self._repo.next_position()

        for currency in sorted(by_currency):
            rows = by_currency[currency]
            account_id = request.account_map[currency]
            to_insert = []
            for row in rows:
                if row.deduplication_hash in existing or row.deduplication_hash in seen:
                    continue
                seen.add(row.deduplication_hash)
                to_insert.append(row)
            skipped = len(rows) - len(to_insert)
            dates = [r.date_posted for r in rows]

            batch = await self._repo.add_batch(
                ImportBatch(
                    account_id=account_id,
                    provider=request.provider,
                    source_file=request.source_file,
                    stored_file=request.stored_file,
                    period_start=min(dates) if dates else None,
                    period_end=max(dates) if dates else None,
                    closing_balance=None,
                    inserted_count=len(to_insert),
                    duplicate_count=skipped,
                )
            )

            for row in to_insert:
                txn = await self._txn_repo.add(
                    TransactionCreate(
                        account_id=account_id,
                        date=datetime.combine(row.date_posted, datetime.min.time()),
                        amount=row.amount if row.type == "transfer" else abs(row.amount),
                        currency=currency,
                        type=row.type,
                        category_id=row.category_id,
                        description=row.description,
                        bank_description=row.bank_description,
                        note=row.note,
                        merchant=row.merchant,
                        source=request.provider,
                        counterpart_account_id=row.counterpart_account_id,
                        deduplication_hash=row.deduplication_hash,
                        import_batch_id=batch.id,
                    )
                )
                all_transactions.append(txn)

            rules_created_here = 0
            for row in to_insert:
                if not row.save_rule or not row.rule_pattern:
                    continue
                self._repo.add_rule(
                    ImportRule(
                        pattern=row.rule_pattern,
                        amount=row.amount if row.rule_match_amount else None,
                        mode=row.rule_mode,
                        description=row.description,
                        merchant=row.merchant,
                        category_id=row.category_id,
                        transfer_account_id=row.counterpart_account_id if row.type == "transfer" else None,
                        position=next_position,
                    )
                )
                next_position += 1
                rules_created_here += 1
            total_rules_created += rules_created_here

            batch_results.append(
                ImportCommitBatchResult(
                    batch_id=batch.id,
                    currency=currency,
                    account_id=account_id,
                    inserted=len(to_insert),
                    skipped_duplicates=skipped,
                )
            )

        await self._repo.commit()
        logger.info(
            "Grouped import committed: provider=%s currencies=%s total_inserted=%d rules=%d",
            request.provider, sorted(by_currency), len(all_transactions), total_rules_created,
        )

        await self._embed_transactions(all_transactions)

        return ImportCommitGroupedResponse(
            batches=batch_results,
            total_inserted=len(all_transactions),
            total_skipped_duplicates=sum(b.skipped_duplicates for b in batch_results),
            rules_created=total_rules_created,
        )
