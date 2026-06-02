import pytest
from datetime import datetime
from unittest.mock import patch
import re
from app.services.command import CommandService

# Mocking datetime to ensure "today" is always 2024-05-20 (a Monday)
FIXED_NOW = datetime(2024, 5, 20)

@pytest.fixture
def mock_now():
    with patch('app.services.command.datetime') as mock_date:
        mock_date.now.return_value = FIXED_NOW
        yield mock_date


def test_resolve_add_basic():
    text = "/taskadd Buy milk"
    response = CommandService.resolve(text)
    assert response.status == "ok"
    assert response.commands[0].command == "add"
    assert response.commands[0].arguments["task"] == "Buy milk"


def test_resolve_add_with_quotes_and_flags():
    text = '/taskadd "Study Kubernetes" -t learning -r weekly -p high'
    response = CommandService.resolve(text)
    assert response.status == "ok"
    cmd = response.commands[0]
    assert cmd.arguments["task"] == "Study Kubernetes"
    assert cmd.arguments["tags"] == "learning"
    assert cmd.arguments["recurrence"] == "weekly"
    assert cmd.arguments["priority"] == "high"


def test_resolve_extracts_today_from_title(mock_now):
    """Test that 'today' inside the text is extracted as a deadline."""
    text = "/task add Buy milk today"
    response = CommandService.resolve(text)

    assert response.status == "ok"
    cmd = response.commands[0]
    assert cmd.arguments["task"] == "Buy milk"
    assert cmd.arguments["deadline"] == "2024-05-20"


def test_resolve_with_nlp_extraction():
    # Test implicit date and priority extraction from title string
    text = "/taskadd Buy milk tomorrow urgently"
    response = CommandService.resolve(text)
    assert response.status == "ok"
    args = response.commands[0].arguments
    assert args["task"] == "Buy milk"
    assert args["priority"] == "high"
    assert re.match(r"\d{4}-\d{2}-\d{2}", args["deadline"])


def test_resolve_with_text_cleaning():
    # Test stripping of filler words like "remind me to"
    text = "/taskadd please remind me to call John"
    response = CommandService.resolve(text)
    assert response.commands[0].arguments["task"] == "call John"


def test_resolve_deadline_mock(mock_now):
    # Testing the specific mock logic for "sunday"
    text = "/ta Buy milk -d sunday"
    response = CommandService.resolve(text)
    assert response.commands[0].arguments["deadline"] == "2024-05-26"


def test_resolve_list_filters():
    text = "/tasklist -s open -p high --limit 5"
    response = CommandService.resolve(text)
    assert response.status == "ok"
    args = response.commands[0].arguments
    assert args["status"] == "open"
    assert args["priority"] == "high"
    assert args["limit"] == "5"


def test_resolve_update_with_id():
    text = "/tu 42 -p high -title 'New Title'"
    response = CommandService.resolve(text)
    assert response.status == "ok"
    args = response.commands[0].arguments
    assert args["id"] == "42"
    assert args["priority"] == "high"
    assert args["title"] == "New Title"


def test_resolve_done_and_delete_aliases():
    # Testing different aliases for complete and delete
    cmds = [("/done 123", "complete"), ("/taskrm 456", "delete")]
    for cmd_str, action in cmds:
        response = CommandService.resolve(cmd_str)
        assert response.status == "ok"
        assert response.commands[0].command == action
        assert response.commands[0].arguments["id"] in ["123", "456"]


def test_resolve_corner_case_not_parsed():
    # Natural language that isn't a command
    text = "Give me a chocolate cake recipe"
    response = CommandService.resolve(text)
    assert response.status == "not_parsed"
    assert len(response.commands) == 0


def test_resolve_corner_case_empty():
    response = CommandService.resolve("   ")
    assert response.status == "not_parsed"


def test_resolve_corner_case_missing_args():
    # Commands that require positional arguments should fail if empty
    bad_commands = ["/taskadd", "/taskupdate", "/taskdone", "/taskdelete"]
    for cmd in bad_commands:
        response = CommandService.resolve(cmd)
        assert response.status == "not_parsed", f"Command {cmd} should have failed"


def test_resolve_corner_case_unknown_flags():
    # Unknown flags should be treated as part of the positional arguments (task name)
    text = "/taskadd Water plants -unknown flag"
    response = CommandService.resolve(text)
    assert response.status == "ok"
    assert "-unknown" in response.commands[0].arguments["task"]
    assert "flag" in response.commands[0].arguments["task"]


def test_resolve_corner_case_flag_no_value():
    # A flag at the end of the string without a value
    text = "/tasklist -p"
    response = CommandService.resolve(text)
    assert response.status == "ok"
    assert response.commands[0].arguments["priority"] is True


def test_resolve_note_add():
    # Verifying the new registry picks up notes too
    text = "/note Important info -t work"
    response = CommandService.resolve(text)
    assert response.status == "ok"
    assert response.commands[0].type == "note"
    assert response.commands[0].arguments["tags"] == "work"


def test_resolve_multiple_commands_in_one_message(mock_now):
    text = "/event Kenai's birthday on Saturday /task buy present tomorrow"
    response = CommandService.resolve(text)

    assert response.status == "ok"
    assert len(response.commands) == 2

    event_command = response.commands[0]
    task_command = response.commands[1]

    assert event_command.type == "event"
    assert event_command.command == "add"
    assert event_command.arguments["title"] == "Kenai's birthday"
    assert event_command.arguments["deadline"] == "2024-05-25"

    assert task_command.type == "task"
    assert task_command.command == "add"
    assert task_command.arguments["task"] == "buy present"
    assert task_command.arguments["deadline"] == "2024-05-21"


def test_resolve_extracts_tomorrow_from_title(mock_now):
    """Test that 'tomorrow' is extracted correctly."""
    text = "/task add Finish report tomorrow"
    response = CommandService.resolve(text)

    assert response.status == "ok"
    cmd = response.commands[0]
    assert cmd.arguments["task"] == "Finish report"
    assert cmd.arguments["deadline"] == "2024-05-21"


def test_resolve_normalises_date_flag(mock_now):
    """Test that explicit date flags are also normalized."""
    text = "/task add Go to gym -d tomorrow"
    response = CommandService.resolve(text)

    assert response.status == "ok"
    cmd = response.commands[0]
    assert cmd.arguments["deadline"] == "2024-05-21"


def test_resolve_extracts_weekday(mock_now):
    """Test that weekdays (e.g., 'on Friday') are extracted."""
    # 2024-05-20 is Monday, so Friday is 2024-05-24
    text = "/task add Team lunch on Friday"
    response = CommandService.resolve(text)

    assert response.status == "ok"
    cmd = response.commands[0]
    assert cmd.arguments["task"] == "Team lunch"
    assert cmd.arguments["deadline"] == "2024-05-24"


def test_resolve_extracts_priority_and_date(mock_now):
    """Test combined extraction of priority keywords and dates."""
    text = "/task add Fix critical bug asap"
    response = CommandService.resolve(text)

    assert response.status == "ok"
    cmd = response.commands[0]
    assert "critical" not in cmd.arguments["task"]
    assert "asap" not in cmd.arguments["task"]
    assert cmd.arguments["priority"] == "high"
    # 'asap' doesn't map to a date in our logic, but we verify title cleanup
    assert cmd.arguments["task"] == "Fix bug"


def test_resolve_extracts_date_with_other_flags(mock_now):
    """Test extraction when other flags are present at the end."""
    text = "/task add Buy groceries today -p medium"
    response = CommandService.resolve(text)

    assert response.status == "ok"
    cmd = response.commands[0]
    assert cmd.arguments["task"] == "Buy groceries"
    assert cmd.arguments["deadline"] == "2024-05-20"
    assert cmd.arguments["priority"] == "medium"


def test_normalise_date_logic(mock_now):
    """Directly test the normalization logic for relative strings."""
    assert CommandService._normalise_date("in 2 days") == "2024-05-22"
    assert CommandService._normalise_date("next week") == "2024-05-27"
    assert CommandService._normalise_date("Sunday") == "2024-05-26"
    assert CommandService._normalise_date("2025-01-01") == "2025-01-01"
