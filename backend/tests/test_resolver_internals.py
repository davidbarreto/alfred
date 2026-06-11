import pytest
from datetime import datetime
from freezegun import freeze_time
from unittest.mock import patch

from app.assistant.commands.resolver import (
    _split_command_fragments,
    _parse_tokens,
    _extract_args_and_flags,
    _enrich_arguments,
    _normalize_date,
    resolve,
)

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
    def test_event_add(self):
        response = resolve("/event Meeting with team on Friday")
        assert response.status == "ok"
        cmd = response.commands[0]
        assert cmd.type == "event"
        assert cmd.command == "add"

    def test_help_command(self):
        # /help requires_args=True but no validation path skips it — check registry
        response = resolve("/help me please")
        assert response.status == "ok"
        assert response.commands[0].type == "help"

    def test_note_search(self):
        response = resolve("/ns kubernetes notes")
        assert response.status == "ok"
        assert response.commands[0].command == "search"
        assert response.commands[0].arguments["query"] == "kubernetes notes"

    def test_note_list(self):
        response = resolve("/nl")
        assert response.status == "ok"
        assert response.commands[0].command == "list"

    def test_task_list_with_unexpected_positional_arg(self):
        # /tasklist has no arg_keys, so extra positional args go to _raw_args
        # then _enrich_arguments converts _raw_args to task
        response = resolve("/tasklist unexpected-arg")
        assert response.status == "ok"

    def test_task_complete_via_td_alias(self):
        response = resolve("/td 99")
        assert response.status == "ok"
        assert response.commands[0].command == "complete"
        assert response.commands[0].arguments["id"] == "99"

    def test_resolver_field(self):
        response = resolve("/taskadd Test task")
        assert response.commands[0].resolver == "deterministic"

    def test_confidence_field(self):
        response = resolve("/taskadd Test task")
        assert response.commands[0].confidence == 0.99

    def test_raw_text_preserved(self):
        text = "/taskadd Buy milk"
        response = resolve(text)
        assert response.raw_text == text
