import pytest
from datetime import datetime
from freezegun import freeze_time
from unittest.mock import AsyncMock, patch

from unittest.mock import MagicMock

from app.assistant.commands.resolver import (
    _split_command_fragments,
    _parse_tokens,
    _extract_args_and_flags,
    _enrich_arguments,
    _enrich_finance,
    _normalize_date,
    resolve,
)
from app.assistant.intents.intent_service import IntentResult
from app.shared.llm import LlmResponse


def _make_llm_provider() -> MagicMock:
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-2.0-flash"
    return provider

FIXED_NOW = datetime(2024, 5, 20)  # Monday


# ── _split_command_fragments ──────────────────────────────────────────────────

class TestSplitCommandFragments:
    def test_single_command(self):
        fragments = _split_command_fragments("/taskadd Buy milk")
        assert fragments == ["/taskadd Buy milk"]

    def test_multiple_commands(self):
        text = "/taskadd Buy milk /tasklist"
        fragments = _split_command_fragments(text)
        assert len(fragments) == 2
        assert fragments[0] == "/taskadd Buy milk"
        assert fragments[1] == "/tasklist"

    def test_three_commands(self):
        text = "/t Buy milk /td 1 /tasklist"
        fragments = _split_command_fragments(text)
        assert len(fragments) == 3

    def test_empty_string(self):
        assert _split_command_fragments("") == []

    def test_whitespace_only(self):
        assert _split_command_fragments("   ") == []

    def test_no_command_prefix(self):
        fragments = _split_command_fragments("just some text")
        assert fragments == ["just some text"]

    def test_leading_whitespace_stripped(self):
        fragments = _split_command_fragments("  /taskadd Buy milk  ")
        assert len(fragments) == 1
        assert fragments[0] == "/taskadd Buy milk"


# ── _parse_tokens ─────────────────────────────────────────────────────────────

class TestParseTokens:
    def test_simple_space_split(self):
        tokens = _parse_tokens("/taskadd Buy milk")
        assert tokens == ["/taskadd", "Buy", "milk"]

    def test_quoted_string_kept_together(self):
        tokens = _parse_tokens('/taskadd "Buy milk now"')
        assert tokens == ["/taskadd", "Buy milk now"]

    def test_single_quotes(self):
        tokens = _parse_tokens("/tu 42 -title 'New Title'")
        assert "New Title" in tokens

    def test_unclosed_quote_falls_back_to_split(self):
        tokens = _parse_tokens('/taskadd "Buy milk')
        assert len(tokens) >= 2

    def test_empty_string(self):
        tokens = _parse_tokens("")
        assert tokens == []

    def test_multiple_flags(self):
        tokens = _parse_tokens("/taskadd Buy milk -p high -d tomorrow")
        assert "/taskadd" in tokens
        assert "-p" in tokens
        assert "high" in tokens


# ── _extract_args_and_flags ───────────────────────────────────────────────────

class TestExtractArgsAndFlags:
    def test_no_flags_all_positional(self):
        args, flags = _extract_args_and_flags(["Buy", "milk"], {})
        assert args == ["Buy", "milk"]
        assert flags == {}

    def test_known_flag_with_value(self):
        args, flags = _extract_args_and_flags(["-p", "high"], {"-p": "priority"})
        assert args == []
        assert flags == {"priority": "high"}

    def test_long_flag_with_value(self):
        args, flags = _extract_args_and_flags(["--priority", "high"], {"--priority": "priority"})
        assert flags == {"priority": "high"}

    def test_flag_at_end_no_value(self):
        args, flags = _extract_args_and_flags(["-p"], {"-p": "priority"})
        assert flags == {"priority": True}

    def test_mixed_positional_and_flags(self):
        args, flags = _extract_args_and_flags(
            ["Buy", "milk", "-p", "high"], {"-p": "priority"}
        )
        assert args == ["Buy", "milk"]
        assert flags == {"priority": "high"}

    def test_normalized_long_flag_from_short(self):
        # Token "-priority" → normalize → try "--priority" first
        args, flags = _extract_args_and_flags(
            ["-priority", "high"], {"--priority": "priority"}
        )
        assert flags == {"priority": "high"}

    def test_normalized_short_flag_from_long(self):
        # Token "--p" → normalize → try "-p"
        args, flags = _extract_args_and_flags(["--p", "high"], {"-p": "priority"})
        assert flags == {"priority": "high"}

    def test_multiple_flags(self):
        flag_defs = {"-p": "priority", "-d": "deadline", "-t": "tags"}
        args, flags = _extract_args_and_flags(
            ["Buy", "milk", "-p", "high", "-d", "tomorrow", "-t", "shopping"],
            flag_defs,
        )
        assert args == ["Buy", "milk"]
        assert flags == {"priority": "high", "deadline": "tomorrow", "tags": "shopping"}

    def test_unknown_flag_treated_as_positional(self):
        args, flags = _extract_args_and_flags(
            ["Buy", "-unknown", "value"], {"-p": "priority"}
        )
        assert "-unknown" in args
        assert "value" in args


# ── _enrich_arguments ─────────────────────────────────────────────────────────

class TestEnrichArguments:
    @freeze_time(FIXED_NOW)
    def test_normalizes_deadline_string(self):
        args = {"deadline": "tomorrow"}
        result = _enrich_arguments(args)
        assert result["deadline"] == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_normalizes_due_to_deadline(self):
        args = {"due": "tomorrow"}
        result = _enrich_arguments(args)
        assert result["deadline"] == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_due_does_not_overwrite_existing_deadline(self):
        args = {"due": "tomorrow", "deadline": "2024-06-01"}
        result = _enrich_arguments(args)
        assert result["deadline"] == "2024-06-01"

    def test_normalizes_priority_urgent(self):
        args = {"priority": "urgent"}
        result = _enrich_arguments(args)
        assert result["priority"] == "HIGH"

    def test_normalizes_priority_important(self):
        args = {"priority": "important"}
        result = _enrich_arguments(args)
        assert result["priority"] == "MEDIUM"

    def test_joins_raw_args_into_task(self):
        args = {"_raw_args": ["Buy", "milk"]}
        result = _enrich_arguments(args)
        assert result.get("task") == "Buy milk"
        assert "_raw_args" not in result

    @freeze_time(FIXED_NOW)
    def test_extracts_date_from_task_field(self):
        args = {"task": "Buy milk tomorrow"}
        result = _enrich_arguments(args)
        assert result["deadline"] == "2024-05-21"
        assert "tomorrow" not in result["task"]

    @freeze_time(FIXED_NOW)
    def test_extracts_priority_from_task_field(self):
        args = {"task": "Fix critical bug"}
        result = _enrich_arguments(args)
        assert result["priority"] == "HIGH"
        assert "critical" not in result["task"]

    @freeze_time(FIXED_NOW)
    def test_does_not_overwrite_explicit_deadline(self):
        args = {"task": "Buy milk tomorrow", "deadline": "2024-06-01"}
        result = _enrich_arguments(args)
        assert result["deadline"] == "2024-06-01"

    @freeze_time(FIXED_NOW)
    def test_extracts_from_title_field(self):
        args = {"title": "Critical meeting tomorrow"}
        result = _enrich_arguments(args)
        assert result.get("priority") == "HIGH"
        assert result.get("deadline") == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_extracts_from_content_field(self):
        args = {"content": "Important note for today"}
        result = _enrich_arguments(args)
        assert result.get("priority") == "MEDIUM"

    @freeze_time(FIXED_NOW)
    def test_extracts_from_description_field(self):
        args = {"description": "urgent: do this asap"}
        result = _enrich_arguments(args)
        assert result.get("priority") == "HIGH"

    def test_no_enrichment_needed(self):
        args = {"task": "Buy groceries"}
        result = _enrich_arguments(args)
        assert result["task"] == "Buy groceries"

    def test_empty_arguments(self):
        result = _enrich_arguments({})
        assert result == {}


# ── _normalize_date ───────────────────────────────────────────────────────────

class TestNormalizeDateHelper:
    @freeze_time(FIXED_NOW)
    def test_returns_iso_for_tomorrow(self):
        assert _normalize_date("tomorrow") == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_returns_iso_for_absolute_date(self):
        assert _normalize_date("2025-01-15") == "2025-01-15"

    def test_returns_none_for_empty(self):
        assert _normalize_date("") is None

    def test_returns_none_for_none(self):
        assert _normalize_date(None) is None  # type: ignore[arg-type]

    @freeze_time(FIXED_NOW)
    def test_with_date_base(self):
        from datetime import date
        result = _normalize_date("tomorrow", base_date=FIXED_NOW.date())
        assert result == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_with_datetime_base(self):
        result = _normalize_date("tomorrow", base_date=FIXED_NOW)
        assert result == "2024-05-21"

    def test_exception_returns_none(self):
        with patch("app.assistant.commands.resolver.normalize_date", side_effect=Exception("err")):
            result = _normalize_date("2024-01-01")
            assert result is None


# ── resolve — edge cases not covered in test_command_service.py ──────────────

class TestResolveEdgeCases:
    @freeze_time(FIXED_NOW)
    async def test_event_add(self):
        response = await resolve("/event Meeting with team on Friday")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.type == "event"
        assert cmd.command == "add"

    async def test_help_command(self):
        # /help requires_args=True but no validation path skips it — check registry
        response = await resolve("/help me please")
        assert response.status == "ok"
        assert response.commands[0].type == "help"

    async def test_note_search(self):
        response = await resolve("/ns kubernetes notes")
        assert response.status == "ok"
        assert response.commands[0].command == "search"
        assert response.commands[0].args["query"] == "kubernetes notes"

    async def test_note_list(self):
        response = await resolve("/nl")
        assert response.status == "ok"
        assert response.commands[0].command == "list"

    async def test_task_list_with_unexpected_positional_arg(self):
        # /tasklist has no arg_keys, so extra positional args go to _raw_args
        # then _enrich_arguments converts _raw_args to task
        response = await resolve("/tasklist unexpected-arg")
        assert response.status == "ok"

    async def test_task_complete_via_td_alias(self):
        response = await resolve("/td 99")
        assert response.status == "ok"
        assert response.commands[0].command == "complete"
        assert response.commands[0].args["id"] == "99"

    async def test_source_field(self):
        response = await resolve("/taskadd Test task")
        assert response.commands[0].source == "deterministic"

    async def test_confidence_field(self):
        response = await resolve("/taskadd Test task")
        assert response.commands[0].confidence == 1.0

    async def test_raw_text_preserved(self):
        text = "/taskadd Buy milk"
        response = await resolve(text)
        assert response.raw_text == text


# ── _enrich_finance ───────────────────────────────────────────────────────────

class TestEnrichFinance:
    @freeze_time(FIXED_NOW)
    def test_normalizes_from_date(self):
        result = _enrich_finance({"from_date": "yesterday"})
        assert result["from_date"] == "2024-05-19"

    @freeze_time(FIXED_NOW)
    def test_normalizes_to_date(self):
        result = _enrich_finance({"to_date": "tomorrow"})
        assert result["to_date"] == "2024-05-21"

    @freeze_time(FIXED_NOW)
    def test_normalizes_date_field(self):
        result = _enrich_finance({"date": "today"})
        assert result["date"] == "2024-05-20"

    def test_iso_date_unchanged(self):
        result = _enrich_finance({"from_date": "2026-06-01"})
        assert result["from_date"] == "2026-06-01"

    def test_extracts_amount_and_currency_from_description(self):
        result = _enrich_finance({"description": "spent €50 at Restaurant"})
        assert result.get("amount") == 50.0
        assert result.get("currency") == "EUR"

    def test_extracts_merchant_from_description(self):
        result = _enrich_finance({"description": "coffee at Starbucks"})
        assert result.get("merchant") == "Starbucks"

    def test_extracts_type_from_description(self):
        result = _enrich_finance({"description": "paid €30 for lunch"})
        assert result.get("type") == "expense"

    def test_explicit_type_not_overwritten_by_nlp(self):
        result = _enrich_finance({"description": "received 100 dollars", "type": "expense"})
        assert result["type"] == "expense"

    def test_explicit_amount_not_overwritten_by_nlp(self):
        result = _enrich_finance({"description": "spent €50", "amount": "99.00"})
        assert result["amount"] == "99.00"

    def test_no_description_no_nlp_enrichment(self):
        args = {"amount": "50", "type": "expense"}
        result = _enrich_finance(args)
        assert result == {"amount": "50", "type": "expense"}

    def test_enrich_arguments_routes_to_finance_path(self):
        result = _enrich_arguments({"description": "spent €50 at Supermarket"}, cmd_type="finance")
        assert result.get("amount") == 50.0
        assert result.get("type") == "expense"

    def test_enrich_arguments_non_finance_not_routed_to_finance(self):
        # Non-finance path should not extract amount/currency from description
        result = _enrich_arguments({"description": "buy €50 groceries urgent"})
        assert "amount" not in result
        assert result.get("priority") == "HIGH"


# ── resolve — finance commands ────────────────────────────────────────────────

class TestResolveFinanceCommands:

    async def test_expense_alias_sets_implicit_type(self):
        response = await resolve("/expense coffee")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.type == "finance"
        assert cmd.command == "transaction_add"
        assert cmd.args["type"] == "expense"

    async def test_income_alias_sets_implicit_type(self):
        response = await resolve("/income salary")
        assert response.status == "ok"
        assert response.commands[0].args["type"] == "income"

    async def test_exp_short_alias(self):
        response = await resolve("/exp groceries")
        assert response.status == "ok"
        assert response.commands[0].command == "transaction_add"
        assert response.commands[0].args["type"] == "expense"

    async def test_inc_short_alias(self):
        response = await resolve("/inc salary")
        assert response.status == "ok"
        assert response.commands[0].args["type"] == "income"

    async def test_explicit_type_flag_overrides_implicit(self):
        response = await resolve("/expense refund --type income")
        assert response.status == "ok"
        assert response.commands[0].args["type"] == "income"

    async def test_transaction_add_with_flags(self):
        response = await resolve("/tra coffee -a 4.50 -m Starbucks")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "transaction_add"
        assert cmd.args["amount"] == "4.50"
        assert cmd.args["merchant"] == "Starbucks"
        assert cmd.args["description"] == "coffee"

    async def test_transaction_list(self):
        response = await resolve("/transactions")
        assert response.status == "ok"
        assert response.commands[0].command == "transaction_list"
        assert response.commands[0].type == "finance"

    async def test_transaction_list_with_filters(self):
        response = await resolve('/trl -tp expense --period "this month"')
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "transaction_list"
        assert cmd.args["type"] == "expense"
        assert cmd.args["period"] == "this month"

    async def test_transaction_delete(self):
        response = await resolve("/trd 42")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "transaction_delete"
        assert cmd.args["id"] == "42"

    async def test_transaction_update(self):
        response = await resolve("/tru 10 -a 99.00 -m Supermarket")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "transaction_update"
        assert cmd.args["id"] == "10"
        assert cmd.args["amount"] == "99.00"
        assert cmd.args["merchant"] == "Supermarket"

    async def test_spending_report_with_period(self):
        response = await resolve("/sr this month")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "spending_report"
        assert cmd.args["period"] == "this month"

    async def test_spending_report_alias_spent(self):
        response = await resolve("/spent last month")
        assert response.status == "ok"
        assert response.commands[0].command == "spending_report"

    async def test_spending_average_alias(self):
        response = await resolve("/sav last month")
        assert response.status == "ok"
        assert response.commands[0].command == "spending_average"
        assert response.commands[0].args["period"] == "last month"

    async def test_spending_top_with_period(self):
        response = await resolve("/stp this week")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "spending_top"
        assert cmd.args["period"] == "this week"

    async def test_budget_add_with_flags(self):
        response = await resolve("/budget Monthly food -a 300 --period monthly")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "budget_add"
        assert cmd.args["name"] == "Monthly food"
        assert cmd.args["amount"] == "300"
        assert cmd.args["period"] == "monthly"

    async def test_budget_list(self):
        response = await resolve("/budgets")
        assert response.status == "ok"
        assert response.commands[0].command == "budget_list"

    async def test_budget_list_short_alias(self):
        response = await resolve("/bl")
        assert response.status == "ok"
        assert response.commands[0].command == "budget_list"

    async def test_budget_remaining_with_period(self):
        response = await resolve("/br this month")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "budget_remaining"
        assert cmd.args["period"] == "this month"

    async def test_balance_forecast(self):
        response = await resolve("/forecast this month")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.command == "balance_forecast"
        assert cmd.args["period"] == "this month"

    async def test_balance_forecast_short_alias(self):
        response = await resolve("/bfc")
        assert response.status == "ok"
        assert response.commands[0].command == "balance_forecast"

    @freeze_time(FIXED_NOW)
    async def test_date_flag_normalized(self):
        response = await resolve("/tra coffee --date yesterday")
        assert response.status == "ok"
        assert response.commands[0].args["date"] == "2024-05-19"

    @freeze_time(FIXED_NOW)
    async def test_from_to_date_flags_normalized(self):
        response = await resolve("/trl --from yesterday --to today")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.args["from_date"] == "2024-05-19"
        assert cmd.args["to_date"] == "2024-05-20"

    async def test_nlp_enriches_description_with_amount_and_merchant(self):
        response = await resolve("/expense spent €50 at Supermarket")
        cmd = response.commands[0]
        assert cmd.args.get("amount") == 50.0
        assert cmd.args.get("currency") == "EUR"
        assert cmd.args.get("merchant") == "Supermarket"
        assert cmd.args["type"] == "expense"

    async def test_finance_enrichment_does_not_extract_priority(self):
        # _enrich_finance runs extract_finance_entities, not extract_entities,
        # so priority keywords in description never produce a priority field.
        response = await resolve("/expense critical coffee urgent")
        cmd = response.commands[0]
        assert "priority" not in cmd.args

    async def test_finance_enrichment_does_not_extract_deadline(self):
        response = await resolve("/expense coffee")
        assert "deadline" not in response.commands[0].args


# ── resolve — intent detection fallback ──────────────────────────────────────

class TestResolveWithIntent:

    async def test_no_session_returns_not_parsed_for_natural_language(self):
        response = await resolve("Buy milk tomorrow")
        assert response.status == "not_parsed"
        assert response.commands == []

    async def test_no_llm_provider_returns_not_parsed(self):
        response = await resolve("Buy milk tomorrow", session=AsyncMock())
        assert response.status == "not_parsed"

    async def test_empty_text_returns_not_parsed_even_with_session(self):
        response = await resolve("   ", session=AsyncMock(), llm_provider=_make_llm_provider())
        assert response.status == "not_parsed"

    async def test_slash_command_uses_deterministic_path_ignores_session(self):
        response = await resolve("/taskadd Buy milk", session=AsyncMock())
        assert response.commands[0].source == "deterministic"
        assert response.commands[0].confidence == 1.0

    async def test_intent_above_threshold_returns_intent_detection(self):
        mock_session = AsyncMock()
        intent_result = IntentResult(intent="task.add", confidence=0.85)
        extracted = {"title": "Buy milk", "due_date": None, "priority": None}

        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)), \
             patch("app.assistant.commands.resolver.extract_args", new=AsyncMock(return_value=extracted)):
            response = await resolve("Buy milk tomorrow", session=mock_session, llm_provider=_make_llm_provider())

        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.source == "intent_detection"
        assert cmd.type == "task"
        assert cmd.command == "add"
        assert cmd.confidence == 0.85
        assert cmd.args == extracted

    async def test_intent_below_threshold_returns_unknown_source(self):
        mock_session = AsyncMock()
        intent_result = IntentResult(intent="task.add", confidence=0.5)

        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)):
            response = await resolve("ambiguous text", session=mock_session, llm_provider=_make_llm_provider())

        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.source == "unknown"
        assert cmd.type == "task"
        assert cmd.command == "add"
        assert cmd.confidence == 0.5
        assert cmd.args == {}

    async def test_unknown_intent_returns_unknown_type_and_command(self):
        mock_session = AsyncMock()
        intent_result = IntentResult(intent="unknown", confidence=0.55)

        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)):
            response = await resolve("some random text", session=mock_session, llm_provider=_make_llm_provider())

        cmd = response.commands[0]
        assert cmd.type == "unknown"
        assert cmd.command == "unknown"
        assert cmd.source == "unknown"

    async def test_extract_args_not_called_below_threshold(self):
        mock_session = AsyncMock()
        intent_result = IntentResult(intent="task.add", confidence=0.5)
        mock_extract = AsyncMock()

        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)), \
             patch("app.assistant.commands.resolver.extract_args", new=mock_extract):
            await resolve("ambiguous", session=mock_session, llm_provider=_make_llm_provider())

        mock_extract.assert_not_called()
