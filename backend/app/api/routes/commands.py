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
    NoteServiceDep,
    RecurringTransactionServiceDep,
    TaskServiceDep,
    TransactionServiceDep,
)

router = APIRouter(prefix="/commands", tags=["commands"], dependencies=[Depends(require_auth)])


@router.post("/resolve", response_model=CommandResolveResponse)
async def resolve_command(request: CommandResolveRequest):
    return resolve(request.text, command=request.command, args=request.args)


@router.post("/execute", response_model=CommandExecuteResponse)
async def execute_command(
    request: CommandExecuteRequest,
    task_service: TaskServiceDep,
    note_service: NoteServiceDep,
    event_service: CalendarEventServiceDep,
    transaction_service: TransactionServiceDep,
    account_service: AccountServiceDep,
    budget_service: BudgetServiceDep,
    recurring_service: RecurringTransactionServiceDep,
):
    result = await execute(
        cmd_type=request.type,
        command=request.command,
        arguments=request.arguments,
        task_service=task_service,
        note_service=note_service,
        event_service=event_service,
        transaction_service=transaction_service,
        account_service=account_service,
        budget_service=budget_service,
        recurring_service=recurring_service,
    )
    return CommandExecuteResponse(type=request.type, command=request.command, status="ok", result=result)