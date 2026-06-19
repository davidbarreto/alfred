from __future__ import annotations

from datetime import datetime
from typing import Any


def _fmt_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%a %d %b at %H:%M")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).strftime("%a %d %b at %H:%M")
        except ValueError:
            return value
    return str(value)


def format_result_message(cmd_type: str, command: str, result: Any) -> str | None:
    if not isinstance(result, dict):
        return None

    if cmd_type == "event":
        if command == "add":
            title = result.get("title", "Event")
            start = result.get("start_datetime")
            return f"Done! '{title}' added to your calendar for {_fmt_dt(start)}."
        if command == "update":
            title = result.get("title", "Event")
            return f"Event '{title}' updated."
        if command == "delete":
            return "Event removed from your calendar."

    if cmd_type == "task":
        if command == "add":
            title = result.get("title", "Task")
            deadline = result.get("deadline")
            suffix = f" (due {_fmt_dt(deadline)})" if deadline else ""
            return f"Task '{title}' added{suffix}."
        if command == "complete":
            title = result.get("title", "Task")
            return f"Task '{title}' marked as done."
        if command == "update":
            title = result.get("title", "Task")
            return f"Task '{title}' updated."
        if command == "delete":
            return "Task removed."

    if cmd_type == "note":
        if command == "add":
            title = result.get("title") or "Note"
            return f"Note '{title}' saved."
        if command == "update":
            return "Note updated."
        if command == "delete":
            return "Note removed."

    if cmd_type == "finance":
        if command == "transaction_add":
            amount = result.get("amount", "")
            currency = result.get("currency", "")
            merchant = result.get("merchant", "")
            parts = [str(amount), currency, f"at {merchant}" if merchant else ""]
            return f"Transaction recorded: {' '.join(p for p in parts if p).strip()}."
        if command == "budget_add":
            return "Budget set."

    return None
