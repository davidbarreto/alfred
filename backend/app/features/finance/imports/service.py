import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.schemas import EmbeddingCreate, EmbeddingSearchRequest
from app.features.core.embeddings.service import EmbeddingService
from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import AccountFilters
from app.features.finance.accounts.tables import Account
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.exchange_rates.service import ExchangeRateService
from app.features.finance.imports.prompts import CATEGORIZE_SYSTEM_PROMPT, CATEGORIZE_USER_PROMPT
from app.features.finance.imports.repository import ImportRepository
from app.features.finance.imports.schemas import (
    CurrencyCandidateAccount,
    CurrencyDetection,
    DetectCurrenciesResponse,
    ImportBatchFilters,
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
    InstallmentPlanActionPreview,
)
from app.features.finance.imports.tables import ImportBatch, ImportRule
from app.features.finance.installment_plans.repository import InstallmentPlanRepository
from app.features.finance.installment_plans.service import InstallmentPlanService
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import TransactionCreate
from app.features.finance.transactions.service import build_mirror_transaction_create
from app.features.finance.transactions.tables import Transaction
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
        exchange_rate_service: ExchangeRateService,
        llm_provider: LlmProvider | None = None,
        file_storage: FileStorage | None = None,
    ) -> None:
        self._session = session
        self._repo = ImportRepository(session)
        self._txn_repo = TransactionRepository(session)
        self._category_repo = CategoryRepository(session)
        self._account_repo = AccountRepository(session)
        self._installment_plan_repo = InstallmentPlanRepository(session)
        self._installment_plans = InstallmentPlanService(session)
        self._parsers = parsers
        self._embeddings = embedding_service
        self._fx = exchange_rate_service
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
        rules = await self._repo.list_rules()
        self._apply_rule_types(rows, rules)
        await self._mark_duplicates(account_id, rows)
        categories = {c.id: c.name for c in await self._category_repo.list()}
        self._apply_rules(rows, rules, categories)
        await self._apply_knn(rows, categories)
        await self._apply_llm(rows, categories)

        self._apply_review_reasons(rows, statement.rows)

        installment_plan_actions = await self._build_installment_plan_actions(
            account_id, statement.installment_plans_opened
        )
        await self._apply_installment_plan_row_matches(account_id, rows)

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
            installment_plan_actions=installment_plan_actions,
        )

    async def _build_installment_plan_actions(
        self, account_id: int, signals: list
    ) -> list[InstallmentPlanActionPreview]:
        """Read-only preview of what committing would do for each plan_ref found in
        the PDF's installment schedule table -- nothing is created here (see
        _apply_installment_plan_actions, commit-only). Already-tracked plans (from a
        prior import) are surfaced with already_tracked=True and no match lookup,
        since matching/placeholder handling only ever happens once, at creation."""
        actions: list[InstallmentPlanActionPreview] = []
        for signal in signals:
            existing_plan = await self._installment_plan_repo.get_by_account_and_plan_ref(
                account_id, signal.plan_ref
            )
            matched = None
            if existing_plan is None and signal.original_amount is not None:
                matched = await self._txn_repo.find_unmatched_transaction(
                    account_id, signal.description, signal.original_amount
                )
            actions.append(
                InstallmentPlanActionPreview(
                    plan_ref=signal.plan_ref,
                    description=signal.description,
                    total_installments=signal.total_installments,
                    original_amount=signal.original_amount,
                    already_tracked=existing_plan is not None,
                    matched_transaction_id=matched.id if matched else None,
                    matched_transaction_summary=(
                        f"{matched.date.date().isoformat()} {matched.amount} {matched.bank_description or ''}".strip()
                        if matched
                        else None
                    ),
                )
            )
        return actions

    async def _apply_installment_plan_row_matches(
        self, account_id: int, rows: list[ImportPreviewRow]
    ) -> None:
        """Generic check, independent of provider: does this new row's own
        (description, amount) match an already-open plan's original lump sum that
        hasn't been matched yet? Runs for every import (CSV or PDF), which is what
        makes matching independent of import order -- a CSV landing before OR after
        the PDF that created the plan both resolve the same way, since the plan
        already exists in the DB by the time either side's row is processed."""
        for row in rows:
            if row.status != "new":
                continue
            matched_plan = await self._txn_repo.find_open_plan_match(
                account_id, row.bank_description, abs(row.amount)
            )
            if matched_plan is not None:
                row.supersedes_installment_plan_id = matched_plan.id

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

    def _link_transfer_pairs(
        self, pair_candidates: dict[str, list[tuple[ImportPreviewRow, int]]]
    ) -> None:
        """Auto-set counterpart_account_id on both legs of a same-event currency
        conversion (see ParsedRow.transfer_pair_key), so a genuinely internal move
        between two tracked accounts nets to zero instead of counting as spend. No FX
        conversion happens here -- we only link the two rows, never their amounts.
        Skips anything a rule already classified, ambiguous groups (not exactly 2 legs),
        legs still resolving to the same account, and duplicate rows.
        """
        for entries in pair_candidates.values():
            if len(entries) != 2:
                continue
            (row_a, account_a), (row_b, account_b) = entries
            if account_a == account_b:
                continue
            if row_a.status != "new" or row_b.status != "new":
                continue
            if row_a.type != "transfer" or row_b.type != "transfer":
                continue
            if row_a.counterpart_account_id is not None or row_b.counterpart_account_id is not None:
                continue
            row_a.counterpart_account_id = account_b
            row_b.counterpart_account_id = account_a

    async def _confirm_transfer_pairs(self, pair_transactions: dict[str, list[Transaction]]) -> None:
        """Once both legs a same-event currency exchange (see _link_transfer_pairs)
        have actually been inserted, set counterpart_transaction_id on each so the
        pairing counts as a confirmed link (see TransactionService.link_transfer) --
        not just an unconfirmed counterpart_account_id guess. A key can resolve to
        fewer than two transactions if one leg was a duplicate/skipped, or to
        mismatched accounts if a row was edited before commit -- either way, no
        confirmed link is safe to make, so it's left as-is (still eligible for the
        user to confirm manually via Find Match).
        """
        for txn_a, txn_b in (entries for entries in pair_transactions.values() if len(entries) == 2):
            if txn_a.account_id == txn_b.account_id:
                continue
            if txn_a.counterpart_account_id != txn_b.account_id or txn_b.counterpart_account_id != txn_a.account_id:
                continue
            await self._txn_repo.set_counterpart_transaction(txn_a.id, txn_b.id)
            await self._txn_repo.set_counterpart_transaction(txn_b.id, txn_a.id)
            logger.info("Transfer pair confirmed at import: id=%d counterpart_id=%d", txn_a.id, txn_b.id)

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
                    installment_juros=parsed_row.installment_juros,
                    installment_duty=parsed_row.installment_duty,
                    note=parsed_row.note,
                    transfer_pair_key=parsed_row.transfer_pair_key,
                )
            )
        return rows

    async def _mark_duplicates(self, account_id: int, rows: list[ImportPreviewRow]) -> None:
        """Flag rows already present in the DB, as well as rows that repeat within this
        same file (e.g. overlapping export date ranges) -- both would otherwise slip
        through preview as "new" and then get silently dropped at commit time, leaving
        the user unable to tell why fewer rows landed than they saw on screen.

        Rows with no balance_after (card-format statements) are matched against the DB
        by content -- (date, bank_description, amount) -- rather than by
        deduplication_hash: the hash's disambiguator for these rows is a per-file
        occurrence counter, which isn't reproducible across separate import runs that
        don't repeat rows in the same relative order (e.g. overlapping export date
        ranges), so hash equality alone was silently missing real duplicates. Any
        existing match at all flags every row sharing that key as a duplicate --
        genuinely repeated same-day/same-amount transactions split across two import
        files are rare enough that they're left for manual force-import rather than
        guessed at automatically.
        """
        no_balance_rows = [r for r in rows if r.balance_after is None]
        existing_keys = await self._txn_repo.get_existing_keys(
            account_id, {r.date_posted for r in no_balance_rows}
        )

        existing = await self._txn_repo.get_existing_dedup_hashes(
            [r.deduplication_hash for r in rows if r.balance_after is not None]
        )
        seen: set[str] = set()
        for row in rows:
            if row.balance_after is None:
                key = (
                    row.date_posted,
                    row.bank_description,
                    row.amount if row.type == "transfer" else abs(row.amount),
                )
                if key in existing_keys:
                    row.status = "duplicate"
                    row.duplicate_reason = "already_imported"
                continue
            if row.deduplication_hash in existing:
                row.status = "duplicate"
                row.duplicate_reason = "already_imported"
            elif row.deduplication_hash in seen:
                row.status = "duplicate"
                row.duplicate_reason = "repeated_in_file"
            else:
                seen.add(row.deduplication_hash)

    def _apply_rule_types(self, rows: list[ImportPreviewRow], rules: list[ImportRule]) -> None:
        """Classify transfer rows before _mark_duplicates runs, so the dedup key's
        amount-sign convention (row.type == "transfer" -> signed, else abs -- see
        _mark_duplicates) already matches what commit() will persist. Without this,
        a row only reclassified as a transfer by _apply_rules (which runs after
        dedup, since it also needs duplicate status to skip already-flagged rows)
        gets stored with a signed amount that a future re-import's abs()-keyed
        duplicate check can never match, silently re-importing it forever.
        """
        for row in rows:
            for rule in rules:
                if not _rule_matches(rule, row.bank_description, row.amount):
                    continue
                if rule.transfer_account_id is not None:
                    row.type = "transfer"
                    row.counterpart_account_id = rule.transfer_account_id
                break

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
                if rule.installment_plan_id is not None:
                    row.installment_plan_id = rule.installment_plan_id
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
                        feature="finance_category_match",
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
            if r.status == "new"
            and r.type != "transfer"
            and r.category_id is None
            and r.suggestion_source is None
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

    async def _sync_account_balance(self, account_id: int, rows: list) -> None:
        """After inserting a batch of imported transactions, bring the account's
        balance up to date. If the batch reported a running balance (ActivoBank
        checking, Banco Inter, Revolut), trust the most recent one directly --
        self-correcting, and cheaper than replaying the full transaction history.
        Otherwise (card-format statements, which never report one) apply the
        batch's net delta incrementally on top of whatever balance is already
        stored.
        """
        if not rows:
            return
        balance_rows = [r for r in rows if r.balance_after is not None]
        if balance_rows:
            latest = max(balance_rows, key=lambda r: r.date_posted)
            await self._account_repo.set_balance(account_id, latest.balance_after)
        else:
            delta = Decimal("0")
            for row in rows:
                # A row superseding a plan's original purchase is inserted at €0.00
                # regardless of its parsed amount (see commit()) -- it must contribute
                # nothing to the balance delta, or the account would be double-counted
                # (once when the real, now-zeroed transaction it stands in for
                # originally posted -- via a prior CSV import or this same one).
                if row.supersedes_installment_plan_id is not None:
                    continue
                amount = row.amount if row.type == "transfer" else abs(row.amount)
                delta += amount if row.type == "income" else -amount
            if delta:
                await self._account_repo.adjust_balance(account_id, delta)
        for row in rows:
            if row.supersedes_installment_plan_id is not None:
                continue
            if row.type == "transfer" and row.counterpart_account_id is not None:
                await self._account_repo.adjust_balance(row.counterpart_account_id, row.amount)

    async def _create_transfer_mirrors(self, transactions: list[Transaction]) -> None:
        """Give a real, visible mirror row (see build_mirror_transaction_create) to
        every imported transfer whose counterpart account has auto_mirror_transfers
        enabled. Runs after the batch commit so every transaction already has an id;
        carries no balance effect of its own (see _sync_account_balance, unchanged).
        """
        counterpart_ids = {
            txn.counterpart_account_id
            for txn in transactions
            if txn.type == "transfer" and txn.counterpart_account_id is not None
        }
        if not counterpart_ids:
            return
        mirrored_accounts = set()
        for account_id in counterpart_ids:
            account = await self._account_repo.get(account_id)
            if account is not None and account.auto_mirror_transfers:
                mirrored_accounts.add(account_id)
        if not mirrored_accounts:
            return
        for txn in transactions:
            if txn.type != "transfer" or txn.counterpart_account_id not in mirrored_accounts:
                continue
            mirror = await self._txn_repo.create(
                build_mirror_transaction_create(txn),
                amount_eur=(-txn.amount_eur if txn.amount_eur is not None else None),
            )
            await self._txn_repo.set_counterpart_transaction(txn.id, mirror.id)
            logger.info(
                "Auto-mirror transaction created: id=%d source_id=%d account_id=%d",
                mirror.id, txn.id, mirror.account_id,
            )

    async def _apply_installment_plan_actions(self, request: ImportCommitRequest) -> None:
        """Get-or-create every plan_ref this import's schedule table touched. Nothing
        to do for an already-tracked plan (matching/placeholder handling only ever
        happens once, right when a plan is first created) -- its future installment
        rows get linked separately via the generic ImportRule match (_apply_rules),
        and its original lump sum (if not yet found) via the generic per-row check
        (_apply_installment_plan_row_matches), both of which run on every import
        regardless of when the plan itself was created.
        """
        opened_date = request.period_start or request.period_end
        if opened_date is None:
            logger.warning(
                "Installment plan actions skipped: no period on import, account_id=%d",
                request.account_id,
            )
            return
        for action in request.installment_plan_actions:
            if action.already_tracked:
                continue
            try:
                await self._apply_one_installment_plan_action(request, action, opened_date)
            except Exception:
                # One action's failure (e.g. an unexpected DB error) must never abort
                # the rest of this loop or the row-insert loop that follows it --
                # a previous incident (fixed by migration 058) showed exactly this:
                # a collision partway through silently discarded every remaining
                # plan AND every transaction in the same commit, including ones with
                # no relation to the failing action at all. Roll back so the session
                # is usable again for the next action.
                await self._session.rollback()
                logger.error(
                    "Installment plan action failed, skipping: account_id=%d plan_ref=%s",
                    request.account_id, action.plan_ref, exc_info=True,
                )

    async def _apply_one_installment_plan_action(
        self, request: ImportCommitRequest, action, opened_date
    ) -> None:
        plan, created = await self._installment_plans.ensure_plan_for_ref(
            account_id=request.account_id,
            plan_ref=action.plan_ref,
            description=action.description,
            total_installments=action.total_installments,
            original_amount=action.original_amount,
            opened_date=opened_date,
        )
        if not created:
            # Race: another request created this plan_ref between preview and
            # commit. Safe to skip -- nothing left for this action to do.
            return

        superseded = False
        if action.matched_transaction_id is not None:
            matched = await self._txn_repo.get(action.matched_transaction_id)
            if matched is not None and matched.amount != 0 and matched.installment_plan_id is None:
                original_amount = matched.amount
                matched.amount = Decimal("0.00")
                matched.note = (
                    f"Original amount {original_amount} {matched.currency}. "
                    f"Split into {action.total_installments} installments ({action.description})."
                )
                matched.installment_plan_id = plan.id
                await self._session.commit()
                logger.info(
                    "Transaction superseded by installment plan: transaction_id=%d plan_id=%d",
                    matched.id, plan.id,
                )
                superseded = True

        if not superseded and action.original_amount is not None:
            # No original_amount means this provider never had a separate lump-sum
            # purchase to begin with (e.g. Nubank's "Parcela M/N" -- each installment
            # row already is the real charge) -- nothing to anchor with a placeholder;
            # the plan's own rows link up via the rule just created, see
            # _relink_new_plan_rows.
            await self._txn_repo.create_placeholder_for_plan(
                account_id=request.account_id,
                plan_id=plan.id,
                description=action.description,
                txn_date=opened_date,
                note="Placeholder — original purchase transaction not found in imported history.",
            )
            logger.info(
                "Installment plan placeholder created: plan_id=%d account_id=%d",
                plan.id, request.account_id,
            )

    async def _relink_new_plan_rows(self, request: ImportCommitRequest) -> None:
        """A plan's auto-created ImportRule doesn't exist yet when _apply_rules runs
        during preview (rule creation only happens here, at commit -- see
        _apply_installment_plan_actions, which just ran) -- so a plan's own first
        captured installment, when it arrives in the SAME import that opens the
        plan, was never tagged with installment_plan_id despite the row and its
        plan both being right here. Re-match just the installment-plan rules (not
        categories, which the user may have already reviewed/edited in the UI)
        against any row still missing it.
        """
        if not request.installment_plan_actions:
            return
        rules = await self._repo.list_rules()
        plan_rules = [r for r in rules if r.installment_plan_id is not None]
        if not plan_rules:
            return
        for row in request.rows:
            if row.installment_plan_id is not None or row.supersedes_installment_plan_id is not None:
                continue
            for rule in plan_rules:
                if _rule_matches(rule, row.bank_description, row.amount):
                    row.installment_plan_id = rule.installment_plan_id
                    break

    async def commit(self, request: ImportCommitRequest) -> ImportCommitResponse:
        await self._apply_installment_plan_actions(request)
        await self._relink_new_plan_rows(request)

        existing = await self._txn_repo.get_existing_dedup_hashes(
            [r.deduplication_hash for r in request.rows]
        )
        # A hash can also repeat WITHIN this request (e.g. overlapping export date
        # ranges produce the same source line twice); the DB's unique constraint would
        # reject the second one and abort the whole batch insert if it weren't caught here.
        seen: set[str] = set()
        to_insert = []
        for row in request.rows:
            if row.force:
                # User confirmed this preview-flagged duplicate is genuinely new; mint a
                # fresh hash so it can't collide with the row it was flagged against.
                row.deduplication_hash = f"{row.deduplication_hash}|forced:{uuid4().hex}"
                to_insert.append(row)
                continue
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
            if row.supersedes_installment_plan_id is not None:
                # This row IS an open plan's original lump-sum purchase (matched at
                # preview time by _apply_installment_plan_row_matches) -- insert it at
                # €0.00 with a note instead of its real amount, same treatment as a
                # plan-creation-time match (see _apply_installment_plan_actions), just
                # discovered later since the plan already existed when this row was
                # parsed.
                amount = Decimal("0.00")
                note = f"Original amount {row.amount} {request.currency}. Split into installments."
            else:
                amount = row.amount if row.type == "transfer" else abs(row.amount)
                note = row.note
            amount_eur = await self._fx.convert_to_eur(amount, request.currency, row.date_posted)
            txn = await self._txn_repo.add(
                TransactionCreate(
                    account_id=request.account_id,
                    date=datetime.combine(row.date_posted, datetime.min.time()),
                    amount=amount,
                    currency=request.currency,
                    type=row.type,
                    category_id=row.category_id,
                    description=row.description,
                    bank_description=row.bank_description,
                    note=note,
                    merchant=row.merchant,
                    source=request.provider,
                    counterpart_account_id=row.counterpart_account_id,
                    balance_after=row.balance_after,
                    deduplication_hash=row.deduplication_hash,
                    import_batch_id=batch.id,
                    installment_plan_id=row.installment_plan_id or row.supersedes_installment_plan_id,
                ),
                amount_eur=amount_eur,
            )
            transactions.append(txn)

        await self._repo.commit()
        for row, txn in zip(to_insert, transactions):
            if row.supersedes_installment_plan_id is not None:
                await self._txn_repo.delete_placeholder_for_plan(row.supersedes_installment_plan_id)
            elif row.installment_plan_id is not None:
                await self._installment_plan_repo.record_capture(
                    row.installment_plan_id,
                    juros=row.installment_juros, imposto_selo=row.installment_duty,
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
        await self._sync_account_balance(request.account_id, to_insert)
        await self._create_transfer_mirrors(transactions)
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

    async def list_batches(self, filters: ImportBatchFilters) -> list[ImportBatchRead]:
        batches = await self._repo.list_batches(filters)
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

    async def list_pending_installments(self, account_id: int):
        return await self._installment_plans.list(account_id=account_id, status="open")

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
        pair_candidates: dict[str, list[tuple[ImportPreviewRow, int]]] = defaultdict(list)
        for currency in sorted(by_currency):
            parsed_rows = by_currency[currency]
            account_id = account_map[currency]
            rows = self._build_rows(account_id, parsed_rows)
            await self._mark_duplicates(account_id, rows)
            self._apply_rules(rows, rules, categories)
            await self._apply_knn(rows, categories)
            await self._apply_llm(rows, categories)
            self._apply_review_reasons(rows, parsed_rows)
            for parsed_row, built_row in zip(parsed_rows, rows):
                if parsed_row.transfer_pair_key:
                    pair_candidates[parsed_row.transfer_pair_key].append((built_row, account_id))

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

        self._link_transfer_pairs(pair_candidates)

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
        rows_by_account: dict[int, list] = defaultdict(list)
        total_rules_created = 0
        next_position = await self._repo.next_position()
        pair_transactions: dict[str, list[Transaction]] = defaultdict(list)

        for currency in sorted(by_currency):
            rows = by_currency[currency]
            account_id = request.account_map[currency]
            to_insert = []
            for row in rows:
                if row.force:
                    row.deduplication_hash = f"{row.deduplication_hash}|forced:{uuid4().hex}"
                    to_insert.append(row)
                    continue
                if row.deduplication_hash in existing or row.deduplication_hash in seen:
                    continue
                seen.add(row.deduplication_hash)
                to_insert.append(row)
            skipped = len(rows) - len(to_insert)
            dates = [r.date_posted for r in rows]
            rows_by_account[account_id].extend(to_insert)

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
                amount = row.amount if row.type == "transfer" else abs(row.amount)
                amount_eur = await self._fx.convert_to_eur(amount, currency, row.date_posted)
                txn = await self._txn_repo.add(
                    TransactionCreate(
                        account_id=account_id,
                        date=datetime.combine(row.date_posted, datetime.min.time()),
                        amount=amount,
                        currency=currency,
                        type=row.type,
                        category_id=row.category_id,
                        description=row.description,
                        bank_description=row.bank_description,
                        note=row.note,
                        merchant=row.merchant,
                        source=request.provider,
                        counterpart_account_id=row.counterpart_account_id,
                        balance_after=row.balance_after,
                        deduplication_hash=row.deduplication_hash,
                        import_batch_id=batch.id,
                    ),
                    amount_eur=amount_eur,
                )
                all_transactions.append(txn)
                if row.transfer_pair_key:
                    pair_transactions[row.transfer_pair_key].append(txn)

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
        for synced_account_id, synced_rows in rows_by_account.items():
            await self._sync_account_balance(synced_account_id, synced_rows)
        await self._create_transfer_mirrors(all_transactions)
        await self._confirm_transfer_pairs(pair_transactions)
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
