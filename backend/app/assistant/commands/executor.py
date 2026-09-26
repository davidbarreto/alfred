import logging
from typing import Any

from fastapi import HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.commands.handlers.account import handle_account
from app.assistant.commands.handlers.assistant import handle_assistant
from app.assistant.commands.handlers.briefing import handle_briefing
from app.assistant.commands.handlers.category import handle_category
from app.assistant.commands.handlers.contact import handle_contact
from app.assistant.commands.handlers.cs import handle_cs
from app.assistant.commands.handlers.event import handle_event
from app.assistant.commands.handlers.finance import handle_finance
from app.assistant.commands.handlers.grammar_scope import handle_grammar_scope
from app.assistant.commands.handlers.help import handle_help
from app.assistant.commands.handlers.interview import handle_interview
from app.assistant.commands.handlers.interview_story import handle_interview_story
from app.assistant.commands.handlers.interview_prep import handle_interview_prep
from app.assistant.commands.handlers.interview_candidate import handle_interview_candidate
from app.assistant.commands.handlers.language import handle_language
from app.assistant.commands.handlers.memory import handle_memory
from app.assistant.commands.handlers.note import handle_note
from app.assistant.commands.handlers.pause import handle_pause
from app.assistant.commands.handlers.recall import handle_recall
from app.assistant.commands.handlers.recurring import handle_recurring
from app.assistant.commands.handlers.reminder import handle_reminder
from app.assistant.commands.handlers.shopping import handle_shopping
from app.assistant.commands.handlers.task import handle_task
from app.assistant.commands.handlers.track import handle_track
from app.assistant.commands.handlers.watcher import handle_alert, handle_watcher
from app.assistant.commands.handlers.weather import handle_weather
from app.assistant.commands.handlers.working_memory import handle_working_memory
from app.features.briefing.history_service import BriefingHistoryService
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.memories.service import MemoryService
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.cs.stats.service import StatsService as CsStatsService
from app.features.cs.study_plans.service import StudyPlanService as CsStudyPlanService
from app.features.finance.accounts.service import AccountService
from app.features.finance.budgets.service import BudgetTargetService
from app.features.finance.categories.service import CategoryService
from app.features.finance.recurring_transactions.service import RecurringTransactionService
from app.features.finance.transactions.service import TransactionService
from app.features.language.chunks.service import ChunkService
from app.features.language.conversation.service import ConversationService
from app.features.language.grammar_scope.service import GrammarScopeService
from app.features.language.production.service import ProductionService
from app.features.language.tracks.service import TrackService
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.contacts.service import ContactService
from app.features.organizer.interviews.processes.service import InterviewProcessService
from app.features.organizer.interviews.stories.service import InterviewStoryService
from app.features.organizer.interviews.prep_questions.service import InterviewPrepQuestionService
from app.features.organizer.interviews.candidate_questions.service import InterviewCandidateQuestionService
from app.features.organizer.notes.service import NoteService
from app.features.organizer.shopping.service import ShoppingService
from app.features.organizer.tasks.service import TaskService
from app.features.core.pause.service import GlobalPauseService

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
    budget_service: BudgetTargetService,
    recurring_service: RecurringTransactionService,
    category_service: CategoryService,
    shopping_service: ShoppingService | None = None,
    track_service: TrackService | None = None,
    chunk_service: ChunkService | None = None,
    working_memory_service: WorkingMemoryService | None = None,
    embedding_service: EmbeddingService | None = None,
    production_service: ProductionService | None = None,
    conversation_service: ConversationService | None = None,
    cs_stats_service: CsStatsService | None = None,
    cs_study_plan_service: CsStudyPlanService | None = None,
    pause_service: GlobalPauseService | None = None,
    contact_service: ContactService | None = None,
    memory_service: MemoryService | None = None,
    interview_process_service: InterviewProcessService | None = None,
    interview_story_service: InterviewStoryService | None = None,
    interview_prep_service: InterviewPrepQuestionService | None = None,
    interview_candidate_service: InterviewCandidateQuestionService | None = None,
    grammar_scope_service: GrammarScopeService | None = None,
    briefing_history_service: BriefingHistoryService | None = None,
    session: AsyncSession | None = None,
    message_id: int | None = None,
) -> Any:
    logger.info("Execute: %s.%s args_keys=%s", cmd_type, command, list(arguments.keys()))

    if cmd_type == "task":
        return await handle_task(
            command, arguments, task_service,
            embedding_service=embedding_service,
            working_memory_service=working_memory_service,
        )

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
            category_service=category_service,
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
        return await handle_language(
            command, arguments, track_service, chunk_service, working_memory_service,
            production_service=production_service,
            conversation_service=conversation_service,
            message_id=message_id,
        )

    if cmd_type == "cs":
        if cs_stats_service is None or working_memory_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CS service not available",
            )
        return await handle_cs(
            command, arguments, cs_stats_service, working_memory_service,
            study_plan_service=cs_study_plan_service,
        )

    if cmd_type == "recall":
        if embedding_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Recall service not available",
            )
        return await handle_recall(command, arguments, embedding_service, note_service=note_service)

    if cmd_type == "weather":
        return await handle_weather(command, arguments)

    if cmd_type == "assistant":
        return await handle_assistant(
            command, arguments, task_service=task_service, event_service=event_service, note_service=note_service,
        )

    if cmd_type == "reminder":
        return await handle_reminder(command, arguments, task_service=task_service)

    if cmd_type == "pause":
        if pause_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pause service not available",
            )
        return await handle_pause(command, arguments, pause_service)

    if cmd_type == "help":
        return handle_help(arguments)

    if cmd_type == "account":
        return await handle_account(command, arguments, account_service)

    if cmd_type == "category":
        return await handle_category(command, arguments, category_service)

    if cmd_type == "recurring":
        return await handle_recurring(command, arguments, recurring_service)

    if cmd_type == "contact":
        if contact_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Contact service not available",
            )
        return await handle_contact(command, arguments, contact_service)

    if cmd_type == "watcher":
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Watcher service not available",
            )
        return await handle_watcher(command, arguments, session)

    if cmd_type == "alert":
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Watcher service not available",
            )
        return await handle_alert(command, arguments, session)

    if cmd_type == "interview":
        if interview_process_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Interview service not available",
            )
        return await handle_interview(command, arguments, interview_process_service)

    if cmd_type == "memory":
        if memory_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service not available",
            )
        return await handle_memory(command, arguments, memory_service)

    if cmd_type == "working_memory":
        if working_memory_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Working memory service not available",
            )
        return await handle_working_memory(command, arguments, working_memory_service)

    if cmd_type == "track":
        if track_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Track service not available",
            )
        return await handle_track(command, arguments, track_service)

    if cmd_type == "grammar_scope":
        if grammar_scope_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Grammar scope service not available",
            )
        return await handle_grammar_scope(command, arguments, grammar_scope_service)

    if cmd_type == "briefing":
        if briefing_history_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Briefing service not available",
            )
        return await handle_briefing(command, arguments, briefing_history_service)

    if cmd_type == "interview_story":
        if interview_story_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Interview story service not available",
            )
        return await handle_interview_story(command, arguments, interview_story_service)

    if cmd_type == "interview_prep":
        if interview_prep_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Interview prep service not available",
            )
        return await handle_interview_prep(command, arguments, interview_prep_service)

    if cmd_type == "interview_candidate":
        if interview_candidate_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Interview candidate service not available",
            )
        return await handle_interview_candidate(command, arguments, interview_candidate_service)

    logger.error("Execute: unknown command type=%s command=%s", cmd_type, command)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown command type: {cmd_type}",
    )
