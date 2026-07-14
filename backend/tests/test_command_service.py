import pytest
from datetime import datetime
from freezegun import freeze_time
import re
from app.assistant.commands.resolver import detect_commands
from app.assistant.commands.resolver import _normalize_date

FIXED_NOW = datetime(2024, 5, 20)

@pytest.fixture
def mock_now():
    with freeze_time(FIXED_NOW):
        yield


async def test_detect_add_basic():
    commands = await detect_commands("/taskadd Buy milk")
    assert len(commands) == 1
    assert commands[0].command == "add"
    assert commands[0].args["title"] == "Buy milk"


async def test_detect_add_with_quotes_and_flags():
    commands = await detect_commands('/taskadd "Study Kubernetes" -t learning -r weekly -p high')
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.args["title"] == "Study Kubernetes"
    assert cmd.args["tags"] == "learning"
    assert cmd.args["recurrence"] == "weekly"
    assert cmd.args["priority"] == "HIGH"


async def test_detect_extracts_today_from_title(mock_now):
    commands = await detect_commands("/task add Buy milk today")
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.args["title"] == "Buy milk"
    assert cmd.args["deadline"] == "2024-05-20"


async def test_detect_with_nlp_extraction():
    commands = await detect_commands("/taskadd Buy milk tomorrow urgently")
    assert len(commands) == 1
    args = commands[0].args
    assert args["title"] == "Buy milk"
    assert args["priority"] == "HIGH"
    assert re.match(r"\d{4}-\d{2}-\d{2}", args["deadline"])


async def test_detect_with_text_cleaning():
    commands = await detect_commands("/taskadd please remind me to call John")
    assert commands[0].args["title"] == "call John"


async def test_detect_deadline_mock(mock_now):
    commands = await detect_commands("/ta Buy milk -d sunday")
    assert commands[0].args["deadline"] == "2024-05-26"


async def test_detect_list_filters():
    commands = await detect_commands("/tasklist -s open -p high --limit 5")
    assert len(commands) == 1
    args = commands[0].args
    assert args["status"] == "open"
    assert args["priority"] == "HIGH"
    assert args["limit"] == "5"


async def test_detect_update_with_id():
    commands = await detect_commands("/tu 42 -p high -title 'New Title'")
    assert len(commands) == 1
    args = commands[0].args
    assert args["id"] == "42"
    assert args["priority"] == "HIGH"
    assert args["title"] == "New Title"


async def test_detect_done_and_delete_aliases():
    cases = [("/done 123", "complete"), ("/taskrm 456", "delete")]
    for cmd_str, action in cases:
        commands = await detect_commands(cmd_str)
        assert len(commands) == 1
        assert commands[0].command == action
        assert commands[0].args["id"] in ["123", "456"]


async def test_detect_no_session_returns_empty_for_natural_language():
    commands = await detect_commands("Give me a chocolate cake recipe")
    assert commands == []


async def test_detect_empty_text_returns_empty():
    commands = await detect_commands("   ")
    assert commands == []


async def test_detect_missing_required_args_returns_empty():
    bad_commands = ["/taskadd", "/taskupdate", "/taskdone", "/taskdelete"]
    for cmd in bad_commands:
        commands = await detect_commands(cmd)
        assert commands == [], f"Command {cmd} should have returned empty"


async def test_detect_unknown_flags_treated_as_positional():
    commands = await detect_commands("/taskadd Water plants -unknown flag")
    assert "-unknown" in commands[0].args["title"]
    assert "flag" in commands[0].args["title"]


async def test_detect_flag_no_value():
    commands = await detect_commands("/tasklist -p")
    assert commands[0].args["priority"] is True


async def test_detect_note_add():
    commands = await detect_commands("/note Important info -t work")
    assert len(commands) == 1
    assert commands[0].type == "note"
    assert commands[0].args["tags"] == "work"


async def test_detect_multiple_commands_in_one_message(mock_now):
    commands = await detect_commands("/event Kenai's birthday on Saturday /task buy present tomorrow")
    assert len(commands) == 2

    event_cmd = commands[0]
    task_cmd = commands[1]

    assert event_cmd.type == "event"
    assert event_cmd.command == "add"
    assert event_cmd.args["title"] == "Kenai's birthday"
    assert event_cmd.args["start"] == "2024-05-25"

    assert task_cmd.type == "task"
    assert task_cmd.command == "add"
    assert task_cmd.args["title"] == "buy present"
    assert task_cmd.args["deadline"] == "2024-05-21"


async def test_detect_extracts_tomorrow_from_title(mock_now):
    commands = await detect_commands("/task add Finish report tomorrow")
    cmd = commands[0]
    assert cmd.args["title"] == "Finish report"
    assert cmd.args["deadline"] == "2024-05-21"


async def test_detect_normalises_date_flag(mock_now):
    commands = await detect_commands("/task add Go to gym -d tomorrow")
    assert commands[0].args["deadline"] == "2024-05-21"


async def test_detect_extracts_weekday(mock_now):
    commands = await detect_commands("/task add Team lunch on Friday")
    cmd = commands[0]
    assert cmd.args["title"] == "Team lunch"
    assert cmd.args["deadline"] == "2024-05-24"


async def test_detect_extracts_priority_and_date(mock_now):
    commands = await detect_commands("/task add Fix critical bug asap")
    cmd = commands[0]
    assert "critical" not in cmd.args["title"]
    assert "asap" not in cmd.args["title"]
    assert cmd.args["priority"] == "HIGH"
    assert cmd.args["title"] == "Fix bug"


async def test_detect_extracts_date_with_other_flags(mock_now):
    commands = await detect_commands("/task add Buy groceries today -p medium")
    cmd = commands[0]
    assert cmd.args["title"] == "Buy groceries"
    assert cmd.args["deadline"] == "2024-05-20"
    assert cmd.args["priority"] == "MEDIUM"


def test_normalise_date_logic(mock_now):
    assert _normalize_date("in 2 days") == "2024-05-22"
    assert _normalize_date("next week") == "2024-05-27"
    assert _normalize_date("Sunday") == "2024-05-26"
    assert _normalize_date("2025-01-01") == "2025-01-01"


# ---------------------------------------------------------------------------
# Command hint path (Telegram entity pre-extraction)
# ---------------------------------------------------------------------------

async def test_hint_basic():
    commands = await detect_commands("/taskadd", command="/taskadd", args="buy milk")
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.type == "task"
    assert cmd.command == "add"
    assert cmd.args["title"] == "buy milk"


async def test_hint_with_flags(mock_now):
    commands = await detect_commands("/taskadd", command="/taskadd", args="buy milk -d sunday -p high")
    cmd = commands[0]
    assert cmd.args["title"] == "buy milk"
    assert cmd.args["deadline"] == "2024-05-26"
    assert cmd.args["priority"] == "HIGH"


async def test_hint_no_args_required_command():
    commands = await detect_commands("/tasklist", command="/tasklist", args=None)
    assert commands[0].command == "list"


async def test_hint_missing_required_args_returns_empty():
    commands = await detect_commands("/taskadd", command="/taskadd", args=None)
    assert commands == []


async def test_hint_unknown_command_returns_empty():
    commands = await detect_commands("/unknown", command="/unknown", args="something")
    assert commands == []


async def test_hint_note_add():
    commands = await detect_commands("/noteadd", command="/noteadd", args="chocolate is good")
    cmd = commands[0]
    assert cmd.type == "note"
    assert cmd.command == "add"
    assert cmd.args["content"] == "chocolate is good"


async def test_hint_skips_text_splitting():
    commands = await detect_commands(
        "/taskadd buy chocolate /noteadd chocolate is good",
        command="/taskadd",
        args="buy chocolate",
    )
    assert len(commands) == 1
    assert commands[0].type == "task"


async def test_hint_long_form_command():
    commands = await detect_commands("/task", command="/task", args="add buy milk")
    cmd = commands[0]
    assert cmd.type == "task"
    assert cmd.command == "add"
    assert cmd.args["title"] == "buy milk"
