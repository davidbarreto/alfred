from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.assistant.commands.executor import execute
from app.assistant.commands.resolver import resolve
from app.assistant.commands.schemas import (
    CommandExecuteRequest,
    CommandExecuteResponse,
    CommandResolveRequest,
    CommandResolveResponse,
)
from app.api.auth import require_auth
from app.dependencies import (
    AccountServiceDep,
    BudgetServiceDep,
    CalendarEventServiceDep,
    CommandExecutionServiceDep,
    DbSessionDep,
    LlmProviderDep,
    NoteServiceDep,
    RecurringTransactionServiceDep,
    TaskServiceDep,
    TransactionServiceDep,
)
from app.features.core.command_executions.schemas import CommandExecutionCreate, CommandExecutionUpdate

router = APIRouter(prefix="/commands", tags=["commands"], dependencies=[Depends(require_auth)])


@router.post("/resolve", response_model=CommandResolveResponse)
async def resolve_command(request: CommandResolveRequest, session: DbSessionDep, llm_provider: LlmProviderDep):
    return await resolve(request.text, command=request.command, args=request.args, session=session, llm_provider=llm_provider)


@router.post("/execute", response_model=CommandExecuteResponse)
async def execute_command(
    request: CommandExecuteRequest,
    cmd_execution_service: CommandExecutionServiceDep,
    task_service: TaskServiceDep,
    note_service: NoteServiceDep,
    event_service: CalendarEventServiceDep,
    transaction_service: TransactionServiceDep,
    account_service: AccountServiceDep,
    budget_service: BudgetServiceDep,
    recurring_service: RecurringTransactionServiceDep,
):
    execution = await cmd_execution_service.create(
        CommandExecutionCreate(
            message_id=request.message_id,
            command_name=f"{request.type}.{request.command}",
            entities=request.args,
        )
    )

    try:
        result: Any = await execute(
            cmd_type=request.type,
            command=request.command,
            arguments=request.args,
            task_service=task_service,
            note_service=note_service,
            event_service=event_service,
            transaction_service=transaction_service,
            account_service=account_service,
            budget_service=budget_service,
            recurring_service=recurring_service,
        )
        entity_id = result.get("id") if isinstance(result, dict) else None
        await cmd_execution_service.update(
            execution.id,
            CommandExecutionUpdate(
                status="success",
                entity_type=request.type,
                entity_id=entity_id,
                executed_at=datetime.now(timezone.utc),
            ),
        )
    except Exception as exc:
        await cmd_execution_service.update(
            execution.id,
            CommandExecutionUpdate(
                status="error",
                error=str(exc),
                executed_at=datetime.now(timezone.utc),
            ),
        )
        raise

    return CommandExecuteResponse(
        command_execution_id=execution.id,
        type=request.type,
        command=request.command,
        status="ok",
        result=result,
    )
