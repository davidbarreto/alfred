import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

logger = logging.getLogger(__name__)

from app.assistant.commands.executor import execute
from app.assistant.commands.resolver import detect_commands
from app.assistant.commands.schemas import (
    CommandDetectRequest,
    CommandDetectResponse,
    CommandExecuteRequest,
    CommandExecuteResponse,
    CommandExtractRequest,
    CommandExtractResponse,
    CommandRespondRequest,
    CommandRespondResponse,
)
from app.assistant.intents.extraction_service import extract_args
from app.assistant.intents.intent_service import get_operation_type
from app.config import get_settings
from app.api.auth import require_auth
from app.dependencies import (
    AccountServiceDep,
    BudgetServiceDep,
    CalendarEventServiceDep,
    CommandExecutionServiceDep,
    DbSessionDep,
    ExtractionLlmProviderDep,
    NoteServiceDep,
    RecurringTransactionServiceDep,
    TaskServiceDep,
    TransactionServiceDep,
)
from app.features.core.command_executions.schemas import CommandExecutionCreate, CommandExecutionFilters, CommandExecutionUpdate
from app.integrations.llm_calls.repository import create_llm_call

router = APIRouter(prefix="/commands", tags=["commands"], dependencies=[Depends(require_auth)])


@router.post("/detect", response_model=CommandDetectResponse)
async def detect_command(
    request: CommandDetectRequest,
    session: DbSessionDep,
) -> CommandDetectResponse:
    logger.info("POST /commands/detect text=%r command=%s", request.text[:80], request.command)
    commands = await detect_commands(
        request.text,
        command=request.command,
        args=request.args,
        session=session,
    )
    intents = [f"{c.type}.{c.command}" for c in commands]
    return CommandDetectResponse(
        operation_type=get_operation_type(intents) if intents else None,
        commands=commands,
        raw_text=request.text,
    )


@router.post("/extract", response_model=CommandExtractResponse)
async def extract_command_args(
    request: CommandExtractRequest,
    session: DbSessionDep,
    llm_provider: ExtractionLlmProviderDep,
) -> CommandExtractResponse:
    logger.info("POST /commands/extract intent=%s text=%r", request.intent, request.text[:80])
    args = await extract_args(request.intent, request.text, llm_provider=llm_provider, session=session)
    return CommandExtractResponse(intent=request.intent, args=args)


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
    logger.info("POST /commands/execute %s.%s", request.type, request.command)
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
        logger.info(
            "Command executed: %s.%s execution_id=%d status=success entity_id=%s",
            request.type, request.command, execution.id, entity_id,
        )
        await cmd_execution_service.update(
            execution.id,
            CommandExecutionUpdate(
                status="success",
                result=result,
                entity_type=request.type,
                entity_id=entity_id,
                executed_at=datetime.now(timezone.utc),
            ),
        )
    except Exception as exc:
        logger.error(
            "Command failed: %s.%s execution_id=%d error=%s",
            request.type, request.command, execution.id, exc,
        )
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


_RESPOND_SYSTEM = (
    "You are Alfred, a helpful personal AI assistant. "
    "Inform the user about the result of the operations below in 1-2 sentences, "
    "natural and friendly tone. Plain text only, no markdown. "
    "If a result is an empty list, say so clearly (e.g. 'You have no tasks right now' or 'Your calendar is clear'). "
    "If a result contains items, summarize them briefly without listing every detail."
)


def _format_result(result: Any) -> str:
    if result is None:
        return "(no data)"
    if isinstance(result, list):
        if not result:
            return "(empty — no items found)"
        return f"({len(result)} item(s)): {result[:3]!r}{'...' if len(result) > 3 else ''}"
    if isinstance(result, dict):
        return repr(result)
    return str(result)


@router.post("/respond", response_model=CommandRespondResponse)
async def respond_to_commands(
    request: CommandRespondRequest,
    session: DbSessionDep,
    cmd_execution_service: CommandExecutionServiceDep,
    llm_provider: ExtractionLlmProviderDep,
) -> CommandRespondResponse:
    logger.info("POST /commands/respond message_id=%d", request.message_id)
    executions = await cmd_execution_service.list(
        CommandExecutionFilters(message_id=request.message_id)
    )
    if not executions:
        logger.warning("No executions found for message_id=%d", request.message_id)
        return CommandRespondResponse(response="")

    lines = []
    for ex in executions:
        if ex.status == "success":
            lines.append(f"- {ex.command_name}: success. Result: {_format_result(ex.result)}")
        else:
            lines.append(f"- {ex.command_name}: failed — {ex.error or 'unknown error'}")

    summary = "\n".join(lines)
    prompt_messages = [{"role": "user", "content": f"Commands executed:\n{summary}"}]
    t0 = time.monotonic()
    llm_response = await llm_provider.complete(prompt_messages, system=_RESPOND_SYSTEM)
    latency_ms = int((time.monotonic() - t0) * 1000)

    await create_llm_call(
        session,
        provider=llm_provider.provider,
        model=llm_provider.model,
        feature="command_respond",
        prompt=[{"role": "system", "content": _RESPOND_SYSTEM}] + prompt_messages,
        response=llm_response.text,
        tokens_input=llm_response.tokens_input,
        tokens_output=llm_response.tokens_output,
        latency_ms=latency_ms,
    )
    return CommandRespondResponse(response=llm_response.text.strip())
