import pytest

from app.assistant.commands.handlers.help import handle_help
from app.assistant.commands.registry import COMMAND_DEFINITIONS


class TestHelpSummary:
    def test_returns_summary_type_when_no_query(self):
        result = handle_help({})
        assert result["type"] == "summary"

    def test_returns_summary_type_when_empty_query(self):
        result = handle_help({"query": ""})
        assert result["type"] == "summary"

    def test_summary_contains_all_groups(self):
        result = handle_help({})
        groups = result["groups"]
        assert "Tasks" in groups
        assert "Notes" in groups
        assert "Finance" in groups
        assert "Shopping" in groups
        assert "Wishlist" in groups
        assert "Calendar" in groups
        assert "Language" in groups
        assert "Memory" in groups
        assert "Weather" in groups
        assert "Assistant" in groups
        assert "Reminders" in groups
        assert "Help" in groups

    def test_each_group_entry_has_command_and_description(self):
        result = handle_help({})
        for group_name, entries in result["groups"].items():
            assert isinstance(entries, list), f"Group '{group_name}' is not a list"
            for entry in entries:
                assert "command" in entry, f"Entry in '{group_name}' missing 'command'"
                assert "description" in entry, f"Entry in '{group_name}' missing 'description'"
                assert entry["command"].startswith("/"), f"Command {entry['command']} missing /"
                assert entry["description"], f"Command {entry['command']} has empty description"

    def test_summary_excludes_action_aliases(self):
        # transaction_add_expense / transaction_add_income have "action" key — should not appear
        result = handle_help({})
        finance_commands = [e["command"] for e in result["groups"].get("Finance", [])]
        assert "/expense" not in finance_commands
        assert "/income" not in finance_commands
        assert "/transactionadd" in finance_commands

    def test_summary_uses_primary_alias(self):
        result = handle_help({})
        task_commands = [e["command"] for e in result["groups"]["Tasks"]]
        assert "/taskadd" in task_commands
        assert "/tasklist" in task_commands


class TestHelpCommandDetail:
    def test_returns_command_type_for_known_alias(self):
        result = handle_help({"query": "taskadd"})
        assert result["type"] == "command"

    def test_returns_correct_command_identifier(self):
        result = handle_help({"query": "taskadd"})
        assert result["command"] == "task.add"

    def test_returns_description(self):
        result = handle_help({"query": "taskadd"})
        assert result["description"]
        assert isinstance(result["description"], str)

    def test_returns_all_aliases(self):
        result = handle_help({"query": "taskadd"})
        assert "/taskadd" in result["aliases"]
        assert "/ta" in result["aliases"]
        assert "/task" in result["aliases"]

    def test_returns_flags(self):
        result = handle_help({"query": "taskadd"})
        flags = result["flags"]
        assert isinstance(flags, list)
        flag_keys = [f["key"] for f in flags]
        assert "deadline" in flag_keys
        assert "priority" in flag_keys
        assert "tags" in flag_keys

    def test_each_flag_has_key_and_aliases(self):
        result = handle_help({"query": "taskadd"})
        for flag in result["flags"]:
            assert "key" in flag
            assert "aliases" in flag
            assert isinstance(flag["aliases"], list)
            assert len(flag["aliases"]) >= 1

    def test_lookup_with_leading_slash(self):
        result = handle_help({"query": "/taskadd"})
        assert result["type"] == "command"
        assert result["command"] == "task.add"

    def test_lookup_by_short_alias(self):
        result = handle_help({"query": "td"})
        assert result["type"] == "command"
        assert result["command"] == "task.complete"

    def test_lookup_expense_alias(self):
        result = handle_help({"query": "expense"})
        assert result["type"] == "command"
        assert result["command"] == "finance.transaction_add_expense"

    def test_help_command_itself(self):
        result = handle_help({"query": "help"})
        assert result["type"] == "command"
        assert result["command"] == "help.help"

    def test_no_flags_for_command_without_flags(self):
        result = handle_help({"query": "pending"})
        assert result["type"] == "command"
        assert result["flags"] == []

    def test_returns_arg_keys(self):
        result = handle_help({"query": "taskadd"})
        assert result["arg_keys"] == ["title"]


class TestHelpNotFound:
    def test_returns_not_found_for_unknown_command(self):
        result = handle_help({"query": "xqzwv"})
        assert result["type"] == "not_found"

    def test_not_found_includes_query(self):
        result = handle_help({"query": "xqzwv"})
        assert result["query"] == "xqzwv"


class TestHelpSearchResults:
    def test_returns_search_results_for_free_text_query(self):
        result = handle_help({"query": "voice conversation a0"})
        assert result["type"] == "search_results"
        assert result["query"] == "voice conversation a0"

    def test_search_results_surface_conversation_and_roleplay(self):
        result = handle_help({"query": "voice conversation a0"})
        commands = [r["command"] for r in result["results"]]
        assert "language.conversation" in commands
        assert "language.conversation_roleplay" in commands

    def test_search_result_entries_have_command_aliases_description(self):
        result = handle_help({"query": "roleplay voice a0"})
        for entry in result["results"]:
            assert "command" in entry
            assert "aliases" in entry
            assert "description" in entry

    def test_search_results_capped_at_limit(self):
        result = handle_help({"query": "language level a0 session code"})
        assert len(result["results"]) <= 3

    def test_no_search_results_falls_back_to_not_found(self):
        result = handle_help({"query": "xqzwv"})
        assert result["type"] == "not_found"
