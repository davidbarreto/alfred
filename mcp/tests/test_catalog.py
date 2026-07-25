import pytest

from app.catalog import build_tools, resolve_call

CATALOG = {
    "task": {
        "add": {
            "action": "add",
            "description": "Create a new task with optional deadline, priority, tags, or recurrence",
            "requires_args": True,
            "arg_keys": ["title"],
            "flags": ["deadline", "priority", "tags", "recurrence"],
            "implicit_flags": {},
        },
        "update": {
            "action": "update",
            "description": "Update a task's title, status, priority, or deadline by ID",
            "requires_args": True,
            "arg_keys": ["id"],
            "flags": ["status", "deadline", "priority", "title", "urgency"],
            "implicit_flags": {},
        },
        "pending": {
            "action": "pending",
            "description": "Show all overdue and today's pending tasks",
            "requires_args": False,
            "arg_keys": [],
            "flags": [],
            "implicit_flags": {},
        },
    },
    "finance": {
        "transaction_add_expense": {
            "action": "transaction_add",
            "description": "Log an expense quickly",
            "requires_args": False,
            "arg_keys": ["description"],
            "flags": ["amount", "category", "merchant", "type", "date", "account", "currency"],
            "implicit_flags": {"type": "expense"},
        },
    },
    "help": {
        "help": {
            "action": "help",
            "description": "Show available commands, or details about a specific command",
            "requires_args": False,
            "arg_keys": ["query"],
            "flags": [],
            "implicit_flags": {},
        },
    },
}


class TestBuildTools:
    def test_one_tool_per_domain(self):
        tools = build_tools(CATALOG)
        assert {t.name for t in tools} == {"alfred_task", "alfred_finance", "alfred_help"}

    def test_action_enum_lists_all_actions_in_domain(self):
        tools = {t.name: t for t in build_tools(CATALOG)}
        task_schema = tools["alfred_task"].inputSchema
        assert set(task_schema["properties"]["action"]["enum"]) == {"add", "update", "pending"}

    def test_params_unioned_across_actions_and_optional(self):
        tools = {t.name: t for t in build_tools(CATALOG)}
        props = tools["alfred_task"].inputSchema["properties"]
        assert set(props.keys()) >= {"title", "id", "deadline", "priority", "tags", "recurrence", "status", "urgency"}
        assert tools["alfred_task"].inputSchema["required"] == ["action"]

    def test_description_mentions_each_action(self):
        tools = {t.name: t for t in build_tools(CATALOG)}
        description = tools["alfred_task"].description
        assert "add" in description
        assert "update" in description
        assert "pending" in description


class TestResolveCall:
    def test_simple_action_passthrough(self):
        cmd_type, action, args = resolve_call(CATALOG, "alfred_task", {"action": "add", "title": "Buy milk"})
        assert cmd_type == "task"
        assert action == "add"
        assert args == {"title": "Buy milk"}

    def test_none_valued_optional_args_are_dropped(self):
        _, _, args = resolve_call(
            CATALOG, "alfred_task", {"action": "add", "title": "Buy milk", "deadline": None}
        )
        assert args == {"title": "Buy milk"}

    def test_missing_required_arg_raises(self):
        with pytest.raises(ValueError, match="missing required argument"):
            resolve_call(CATALOG, "alfred_task", {"action": "add"})

    def test_convenience_action_resolves_real_action_and_implicit_flags(self):
        cmd_type, action, args = resolve_call(
            CATALOG, "alfred_finance", {"action": "transaction_add_expense", "amount": "12.50"}
        )
        assert cmd_type == "finance"
        assert action == "transaction_add"
        assert args == {"amount": "12.50", "type": "expense"}

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            resolve_call(CATALOG, "alfred_nonexistent", {"action": "add"})

    def test_unknown_action_raises(self):
        with pytest.raises(ValueError, match="Unknown action"):
            resolve_call(CATALOG, "alfred_task", {"action": "nonexistent"})

    def test_missing_action_raises(self):
        with pytest.raises(ValueError, match="Unknown action"):
            resolve_call(CATALOG, "alfred_task", {})
