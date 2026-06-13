from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers.event import handle_event
from app.assistant.commands.handlers.finance import handle_finance
from app.assistant.commands.handlers.note import handle_note
from app.assistant.commands.handlers.task import handle_task
from app.features.finance.accounts.service import AccountService
from app.features.finance.budgets.service import BudgetService
from app.features.finance.recurring_transactions.service import RecurringTransactionService
from app.features.finance.transactions.service import TransactionService
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.notes.service import NoteService
from app.features.organizer.tasks.service import TaskService


async def execute(
    cmd_type: str,
    command: str,
    arguments: dict[str, Any],
    task_service: TaskService,
    note_service: NoteService,
    event_service: CalendarEventService,
    transaction_service: TransactionService,
    account_service: AccountService,
    budget_service: BudgetService,
    recurring_service: RecurringTransactionService,
) -> Any:
    if cmd_type == "task":
        return await handle_task(command, arguments, task_service)

    if cmd_type == "note":
        return await handle_note(command, arguments, note_service)

    if cmd_type == "event":
        return await handle_event(command, arguments, event_service)

    if cmd_type == "finance":
        return await handle_finance(
            command,
            arguments,
            transaction_service=transaction_service,
            account_service=account_service,
            budget_service=budget_service,
            recurring_service=recurring_service,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown command type: {cmd_type}",
    )
