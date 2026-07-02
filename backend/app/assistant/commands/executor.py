import logging
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers.assistant import handle_assistant
from app.assistant.commands.handlers.event import handle_event
from app.assistant.commands.handlers.finance import handle_finance
from app.assistant.commands.handlers.help import handle_help
from app.assistant.commands.handlers.language import handle_language
from app.assistant.commands.handlers.note import handle_note
from app.assistant.commands.handlers.recall import handle_recall
from app.assistant.commands.handlers.reminder import handle_reminder
from app.assistant.commands.handlers.shopping import handle_shopping
from app.assistant.commands.handlers.task import handle_task
from app.assistant.commands.handlers.weather import handle_weather
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.finance.accounts.service import AccountService
from app.features.finance.budgets.service import BudgetService
from app.features.finance.recurring_transactions.service import RecurringTransactionService
from app.features.finance.transactions.service import TransactionService
from app.features.language.chunks.service import ChunkService
from app.features.language.tracks.service import TrackService
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.notes.service import NoteService
from app.features.organizer.shopping.service import ShoppingService
from app.features.organizer.tasks.service import TaskService

logger = logging.getLogger(__name__)


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
    shopping_service: ShoppingService | None = None,
    track_service: TrackService | None = None,
    chunk_service: ChunkService | None = None,
    working_memory_service: WorkingMemoryService | None = None,
    embedding_service: EmbeddingService | None = None,
) -> Any:
    logger.info("Execute: %s.%s args_keys=%s", cmd_type, command, list(arguments.keys()))

    if cmd_type == "task":
        return await handle_task(command, arguments, task_service, embedding_service=embedding_service)

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

    if cmd_type in ("shopping", "wishlist"):
        if shopping_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shopping service not available",
            )
        return await handle_shopping(cmd_type, command, arguments, shopping_service)

    if cmd_type == "language":
        if track_service is None or chunk_service is None or working_memory_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Language service not available",
            )
        return await handle_language(command, arguments, track_service, chunk_service, working_memory_service)

    if cmd_type == "recall":
        if embedding_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Recall service not available",
            )
        return await handle_recall(command, arguments, embedding_service)

    if cmd_type == "weather":
        return await handle_weather(command, arguments)

    if cmd_type == "assistant":
        return await handle_assistant(command, arguments, task_service=task_service, event_service=event_service)

    if cmd_type == "reminder":
        return await handle_reminder(command, arguments, task_service=task_service)

    if cmd_type == "help":
        return handle_help(arguments)

    logger.error("Execute: unknown command type=%s command=%s", cmd_type, command)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown command type: {cmd_type}",
    )
