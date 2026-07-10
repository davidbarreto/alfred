import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.features.core.chats.schemas import ChatRequest
from app.features.core.chats.service import (
    ChatService,
    _build_system_prompt,
    _strip_markdown,
    _to_message_dicts,
)
from app.features.core.embeddings.schemas import EmbeddingSearchResult
from app.features.core.messages.schemas import MessageRead
from app.features.core.sessions.tables import Session
from app.features.core.working_memory.schemas import WorkingMemoryRead
from app.features.language.chunks.schemas import ChunkRead, DailyBatchRead
from app.features.language.sessions.tables import LearningSession
from app.shared.llm import LlmResponse


def _make_embedding_result(source_type: str, content: str, similarity: float = 0.9) -> EmbeddingSearchResult:
    return EmbeddingSearchResult(
        id=1,
        source_type=source_type,
        source_id=1,
        content=content,
        model="all-MiniLM-L6-v2",
        dimensions=384,
        embedded_at=datetime(2024, 1, 1),
        similarity=similarity,
    )


def _make_message(content: str, role: str = "user") -> MessageRead:
    return MessageRead(
        id=1,
        session_id=1,
        role=role,
        content=content,
        created_at=datetime(2024, 1, 1),
    )


def _make_llm_provider(text: str = "ok") -> MagicMock:
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-2.0-flash"
    provider.complete = AsyncMock(return_value=LlmResponse(text=text, tokens_input=10, tokens_output=5))
    return provider


def _make_session_row(source: str = "telegram", external_id: str = "user_123") -> Session:
    s = Session()
    s.id = 1
    s.source = source
    s.external_id = external_id
    return s


@pytest.fixture(autouse=True)
def mock_session_repository():
    with patch("app.features.core.chats.service.SessionRepository") as mock_repo_cls:
        mock_repo_cls.return_value.get = AsyncMock(return_value=_make_session_row())
        yield mock_repo_cls


@pytest.fixture(autouse=True)
def mock_language_session_repository():
    with patch("app.features.core.chats.service.LanguageSessionRepository") as mock_cls:
        mock_cls.return_value.get_sessions = AsyncMock(return_value=[])
        yield mock_cls


def _make_language_session(
    chunk_id: int = 42,
    quality_score: float | None = 85.0,
    feedback: dict | None = None,
) -> LearningSession:
    ls = LearningSession()
    ls.id = 1
    ls.track_id = 3
    ls.chunk_id = chunk_id
    ls.session_type = "shadowing"
    ls.feeds_srs = quality_score is not None
    ls.audio_ref = None
    ls.quality_score = quality_score
    ls.ai_feedback_json = feedback or {
        "score": quality_score,
        "summary": "Good overall effort.",
        "strengths": ["clear vowels"],
        "issues": ["'r' sound unclear"],
        "tip": "Relax your tongue for the 'r'.",
    }
    ls.transcript_or_notes = None
    ls.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ls


def _make_wm(key: str = "travel_context", value: str = "Belgium trip") -> WorkingMemoryRead:
    return WorkingMemoryRead(
        id=1, key=key, value=value, importance=None,
        expires_at=None, session_id=None, created_at=datetime(2024, 1, 1),
    )


def _make_chunk(chunk_id: int, text: str = "next phrase", translation: str = "next translation") -> ChunkRead:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ChunkRead(
        id=chunk_id, track_id=3, grammar_scope_id=None, chunk_type="word",
        text=text, translation=translation, example_sentence=None, example_translation=None,
        cefr_level=None, frequency_rank=None, frequency_source=None,
        stability=1.0, difficulty=1.0, due_at=now, last_review_at=None,
        repetitions=0, lapses=0, consecutive_failures=0, state="new",
        prod_stability=0.0, prod_difficulty=5.0, prod_due_at=None, prod_last_review_at=None,
        prod_repetitions=0, prod_lapses=0, prod_consecutive_failures=0, prod_state="new",
        status="active", is_leech=False, created_at=now, updated_at=now,
    )


def _make_batch(track_id: int, chunks: list[ChunkRead]) -> DailyBatchRead:
    return DailyBatchRead(track_id=track_id, track_code="pt", chunks=chunks, total_due=len(chunks))


def _make_service(llm_text: str = "ok") -> tuple[ChatService, MagicMock, AsyncMock, AsyncMock, MagicMock]:
    session = AsyncMock()
    session.add = MagicMock()
    llm_provider = _make_llm_provider(llm_text)
    embedding_service = AsyncMock()
    embedding_service.search = AsyncMock(return_value=[])
    message_service = AsyncMock()
    message_service.list = AsyncMock(return_value=[])
    message_service.create = AsyncMock()
    memory_extraction_service = MagicMock()
    memory_extraction_service.extract_and_save = AsyncMock()
    session_summary_service = MagicMock()
    session_summary_service.get_recent_summaries = AsyncMock(return_value=[])
    working_memory_service = AsyncMock()
    working_memory_service.list = AsyncMock(return_value=[])
    chunk_service = AsyncMock()
    chunk_service.get_daily_batch = AsyncMock(return_value=[])
    production_service = AsyncMock()
    production_service.get_next_task = AsyncMock(return_value=None)
    service = ChatService(
        session=session,
        llm_provider=llm_provider,
        embedding_service=embedding_service,
        message_service=message_service,
        memory_extraction_service=memory_extraction_service,
        session_summary_service=session_summary_service,
        working_memory_service=working_memory_service,
        chunk_service=chunk_service,
        production_service=production_service,
    )
    return service, llm_provider, embedding_service, message_service, memory_extraction_service


class TestChatServiceResponse:
    async def test_returns_llm_response(self):
        service, _, _, message_service, _ = _make_service("Hello from Alfred!")
        message_service.list.return_value = [_make_message("Hello")]
        result, next_practice = await service.chat(ChatRequest(session_id=1))
        assert result == "Hello from Alfred!"
        assert next_practice is None

    async def test_uses_last_user_message_as_agent_input(self):
        service, llm_provider, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("What tasks do I have?")]
        await service.chat(ChatRequest(session_id=1))
        messages = llm_provider.complete.call_args[0][0]
        assert messages[-1]["content"] == "What tasks do I have?"
        assert messages[-1]["role"] == "user"

    async def test_raises_422_when_no_messages_in_session(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            await service.chat(ChatRequest(session_id=1))
        assert exc_info.value.status_code == 422


class TestChatServiceHistory:
    async def test_retrieves_history_cross_session_when_source_known(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        with patch("app.features.core.chats.service.SessionRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get = AsyncMock(return_value=_make_session_row("telegram", "u42"))
            await service.chat(ChatRequest(session_id=42))
        filters = message_service.list.call_args[0][0]
        assert filters.source == "telegram"
        assert filters.external_id == "u42"
        assert filters.session_id is None

    async def test_falls_back_to_session_id_when_source_unknown(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        session_row = _make_session_row()
        session_row.source = None
        session_row.external_id = None
        with patch("app.features.core.chats.service.SessionRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get = AsyncMock(return_value=session_row)
            await service.chat(ChatRequest(session_id=42))
        filters = message_service.list.call_args[0][0]
        assert filters.session_id == 42

    async def test_excludes_current_message_from_history(self):
        service, llm_provider, _, message_service, _ = _make_service()
        msgs = [_make_message("previous"), _make_message("current")]
        message_service.list.return_value = msgs
        with patch("app.features.core.chats.service.SessionRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get = AsyncMock(return_value=_make_session_row())
            await service.chat(ChatRequest(session_id=1))
        messages = llm_provider.complete.call_args[0][0]
        assert messages[-1]["content"] == "current"
        assert len([m for m in messages if m["content"] == "previous"]) == 1

    async def test_requests_history_limit_plus_one_from_repository(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        with patch("app.features.core.chats.service.SessionRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get = AsyncMock(return_value=_make_session_row())
            await service.chat(ChatRequest(session_id=1))
        filters = message_service.list.call_args[0][0]
        assert filters.limit == 11


class TestChatServiceMemorySearch:
    async def test_searches_memories_with_current_message_text(self):
        service, _, embedding_service, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("what did I note about bread?")]
        await service.chat(ChatRequest(session_id=1))
        req = embedding_service.search.call_args[0][0]
        assert req.query == "what did I note about bread?"
        assert set(req.source_types) == {"memory", "note", "task"}

    async def test_empty_memories_still_works(self):
        service, _, embedding_service, message_service, _ = _make_service("ok")
        message_service.list.return_value = [_make_message("hi")]
        embedding_service.search = AsyncMock(return_value=[])
        result, _ = await service.chat(ChatRequest(session_id=1))
        assert result == "ok"


class TestChatServiceMessageSaving:
    async def test_saves_assistant_message_after_reply(self):
        service, _, _, message_service, _ = _make_service("Alfred's reply")
        message_service.list.return_value = [_make_message("hello", role="user")]
        await service.chat(ChatRequest(session_id=5))
        message_service.create.assert_called_once()
        created = message_service.create.call_args[0][0]
        assert created.session_id == 5
        assert created.role == "assistant"
        assert created.content == "Alfred's reply"

    async def test_assistant_message_has_no_meta(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        created = message_service.create.call_args[0][0]
        assert created.meta is None


def _fixed_now(year=2026, month=6, day=17, hour=14, minute=30):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestBuildSystemPrompt:
    def test_includes_real_persona_not_fallback(self):
        prompt = _build_system_prompt([])
        # A string only present in the real persona.md — fails if path is wrong and fallback fires
        assert "Alfred" in prompt and "David" in prompt

    def test_includes_memories(self):
        memories = [_make_embedding_result("memory", "David likes bread")]
        prompt = _build_system_prompt(memories)
        assert "David likes bread" in prompt
        assert "memory" in prompt

    def test_no_memory_section_when_empty(self):
        prompt = _build_system_prompt([])
        assert "Relevant context" not in prompt

    def test_includes_current_datetime(self):
        with patch("app.features.core.chats.service.datetime") as mock_dt:
            mock_dt.now.return_value = _fixed_now()
            prompt = _build_system_prompt([])
        assert "Wednesday, June 17, 2026 at 14:30 UTC" in prompt

    def test_includes_formatting_instructions(self):
        prompt = _build_system_prompt([])
        assert "plain text" in prompt
        assert "Telegram" in prompt

    def test_includes_detected_intents_in_prompt(self):
        prompt = _build_system_prompt([], detected_intents=["event.add"])
        assert "event.add" in prompt
        assert "Parallel command pipeline" in prompt

    def test_no_intent_section_when_none(self):
        prompt = _build_system_prompt([])
        assert "Parallel command pipeline" not in prompt

    def test_command_boundary_included_when_no_intents(self):
        prompt = _build_system_prompt([])
        assert "Never offer to create" in prompt
        assert "slash command" in prompt

    def test_command_boundary_excluded_when_intents_present(self):
        prompt = _build_system_prompt([], detected_intents=["task.add"])
        assert "Never offer to create" not in prompt

    def test_includes_recent_session_summaries(self):
        summaries = [(_fixed_now(), "User discussed event scheduling.")]
        prompt = _build_system_prompt([], recent_summaries=summaries)
        assert "Recent conversations" in prompt
        assert "User discussed event scheduling." in prompt
        assert "June 17, 2026" in prompt

    def test_no_summary_section_when_empty(self):
        prompt = _build_system_prompt([], recent_summaries=[])
        assert "Recent conversations" not in prompt

    def test_summaries_appear_before_memories(self):
        memories = [_make_embedding_result("memory", "Likes coffee")]
        summaries = [(_fixed_now(), "Talked about tasks.")]
        prompt = _build_system_prompt(memories, recent_summaries=summaries)
        assert prompt.index("Recent conversations") < prompt.index("Relevant context from memory")

    def test_intent_section_appears_before_persona(self):
        prompt = _build_system_prompt([], detected_intents=["event.add"])
        assert prompt.index("Parallel command pipeline") < prompt.index("Alfred")


class TestBuildSystemPromptWorkingMemory:
    def test_includes_working_memory_entries(self):
        wm = _make_wm("travel_context", "Belgium next week")
        prompt = _build_system_prompt([], working_memories=[wm])
        assert "Active context" in prompt
        assert "travel_context" in prompt
        assert "Belgium next week" in prompt

    def test_no_active_context_section_when_empty(self):
        prompt = _build_system_prompt([], working_memories=[])
        assert "Active context" not in prompt

    def test_no_active_context_section_when_none(self):
        prompt = _build_system_prompt([])
        assert "Active context" not in prompt

    def test_includes_practice_hint_for_language_practice_without_session(self):
        wm = _make_wm("language:pending", '{"mode": "practice", "chunk_id": 1, "text": "fazer questão de"}')
        prompt = _build_system_prompt([], working_memories=[wm])
        assert "language practice" in prompt.lower()
        assert "coach" in prompt.lower()

    def test_no_practice_hint_for_non_practice_key(self):
        wm = _make_wm("travel_context", "Belgium trip")
        prompt = _build_system_prompt([], working_memories=[wm])
        assert "coach" not in prompt.lower()

    def test_includes_review_hint_for_language_review(self):
        wm = _make_wm("language:pending", '{"mode": "review", "chunk_id": 1, "text": "bonjour"}')
        prompt = _build_system_prompt([], working_memories=[wm])
        assert "vocabulary review" in prompt.lower()

    def test_includes_grade_when_language_session_provided(self):
        wm = _make_wm("language:pending", '{"mode": "practice", "chunk_id": 42}')
        session = _make_language_session(quality_score=87.0)
        prompt = _build_system_prompt([], working_memories=[wm], language_session=session)
        assert "87/100" in prompt
        assert "Practice result" in prompt
        assert "clear vowels" in prompt
        assert "'r' sound unclear" in prompt
        assert "Relax your tongue" in prompt
        assert "coach" in prompt.lower()

    def test_falls_back_to_generic_hint_when_session_has_no_score(self):
        wm = _make_wm("language:pending", '{"mode": "practice", "chunk_id": 42}')
        session = _make_language_session(quality_score=None)
        prompt = _build_system_prompt([], working_memories=[wm], language_session=session)
        assert "Practice result" not in prompt
        assert "language practice" in prompt.lower()

    def test_falls_back_to_generic_hint_when_no_session(self):
        wm = _make_wm("language:pending", '{"mode": "practice", "chunk_id": 42}')
        prompt = _build_system_prompt([], working_memories=[wm], language_session=None)
        assert "Practice result" not in prompt
        assert "language practice" in prompt.lower()

    def test_active_context_appears_before_memories(self):
        wm = _make_wm("travel_context", "Belgium trip")
        mem = _make_embedding_result("memory", "Likes coffee")
        prompt = _build_system_prompt([mem], working_memories=[wm])
        assert prompt.index("Active context") < prompt.index("Relevant context from memory")


class TestChatServiceWorkingMemory:
    async def test_fetches_active_working_memories_on_chat(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        service._working_memory_service.list.assert_called_once()

    async def test_working_memory_appears_in_system_prompt(self):
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_wm("travel_context", "Belgium trip")]
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "travel_context" in system_prompt
        assert "Belgium trip" in system_prompt

    async def test_skips_embedding_search_in_language_practice_mode(self):
        service, _, embedding_service, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", '{"chunk_id": 1, "text": "olá"}')
        ]
        message_service.list.return_value = [_make_message("olá")]
        await service.chat(ChatRequest(session_id=1))
        embedding_service.search.assert_not_called()

    async def test_skips_session_summaries_in_language_practice_mode(self):
        service, _, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", '{"chunk_id": 1, "text": "olá"}')
        ]
        message_service.list.return_value = [_make_message("olá")]
        await service.chat(ChatRequest(session_id=1))
        service._session_summary_service.get_recent_summaries.assert_not_called()

    async def test_runs_full_pipeline_when_no_practice_mode(self):
        service, _, embedding_service, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_wm("travel_context", "Belgium")]
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        embedding_service.search.assert_called_once()

    async def test_deletes_practice_wm_after_chat(self):
        service, _, _, message_service, _ = _make_service()
        wm = _make_wm("language:pending", '{"chunk_id": 42}')
        wm = WorkingMemoryRead(id=99, key=wm.key, value=wm.value, importance=None,
                               expires_at=None, session_id=None, created_at=wm.created_at)
        service._working_memory_service.list.return_value = [wm]
        message_service.list.return_value = [_make_message("a chuva caiu")]
        await service.chat(ChatRequest(session_id=1))
        service._working_memory_service.delete.assert_called_once_with(99)

    async def test_does_not_delete_non_practice_wm(self):
        service, _, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_wm("travel_context", "Belgium")]
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        service._working_memory_service.delete.assert_not_called()


class TestChatServiceLanguagePracticeGrade:
    async def test_queries_language_session_for_chunk_in_wm(self, mock_language_session_repository):
        service, _, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", '{"mode": "practice", "chunk_id": 42, "track_id": 3}')
        ]
        message_service.list.return_value = [_make_message("a chuva caiu")]
        await service.chat(ChatRequest(session_id=1))
        mock_language_session_repository.return_value.get_sessions.assert_called_once()
        filters = mock_language_session_repository.return_value.get_sessions.call_args[0][0]
        assert filters.chunk_id == 42
        assert filters.session_type == "shadowing"
        assert filters.limit == 1

    async def test_grade_appears_in_system_prompt_when_session_found(self, mock_language_session_repository, mock_session_repository):
        mock_language_session_repository.return_value.get_sessions = AsyncMock(
            return_value=[_make_language_session(quality_score=87.0)]
        )
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", '{"mode": "practice", "chunk_id": 42, "track_id": 3}')
        ]
        message_service.list.return_value = [_make_message("a chuva caiu")]
        with patch("app.features.core.chats.service.SessionRepository", mock_session_repository):
            await service.chat(ChatRequest(session_id=1))
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "87/100" in system_prompt
        assert "Practice result" in system_prompt

    async def test_graceful_when_wm_value_is_invalid_json(self, mock_language_session_repository):
        service, _, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", "not-json")
        ]
        message_service.list.return_value = [_make_message("olá")]
        await service.chat(ChatRequest(session_id=1))
        mock_language_session_repository.return_value.get_sessions.assert_not_called()

    async def test_no_session_lookup_when_not_practice_mode(self, mock_language_session_repository):
        service, _, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_wm("travel_context", "Belgium")]
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        mock_language_session_repository.return_value.get_sessions.assert_not_called()


class TestChatServiceLanguageLoop:
    async def test_advances_to_next_chunk_when_remaining(self, mock_language_session_repository):
        service, _, _, message_service, _ = _make_service()
        wm = _make_wm("language:pending", json.dumps({
            "mode": "practice", "chunk_id": 42, "track_id": 3, "track_code": "pt",
            "language_name": "Portuguese", "text": "a chuva caiu", "translation": "it rained",
            "remaining": 3,
        }))
        wm = WorkingMemoryRead(id=99, key=wm.key, value=wm.value, importance=None,
                               expires_at=None, session_id=None, created_at=wm.created_at)
        service._working_memory_service.list.return_value = [wm]
        service._chunk_service.get_daily_batch.return_value = [
            _make_batch(3, [_make_chunk(42), _make_chunk(43, text="outra frase", translation="another phrase")])
        ]
        message_service.list.return_value = [_make_message("a chuva caiu")]

        _, next_practice = await service.chat(ChatRequest(session_id=1))

        service._working_memory_service.delete.assert_called_once_with(99)
        service._working_memory_service.create.assert_called_once()
        created_value = json.loads(service._working_memory_service.create.call_args[0][0].value)
        assert created_value["chunk_id"] == 43
        assert created_value["remaining"] == 2
        assert next_practice is not None
        assert next_practice.chunk_id == 43
        assert next_practice.remaining == 2
        assert next_practice.mode == "practice"
        assert next_practice.track_code == "pt"

    async def test_ends_loop_when_remaining_exhausted(self, mock_language_session_repository):
        service, _, _, message_service, _ = _make_service()
        wm = _make_wm("language:pending", json.dumps({
            "mode": "practice", "chunk_id": 42, "track_id": 3, "track_code": "pt",
            "language_name": "Portuguese", "text": "a chuva caiu", "translation": "it rained",
            "remaining": 1,
        }))
        wm = WorkingMemoryRead(id=99, key=wm.key, value=wm.value, importance=None,
                               expires_at=None, session_id=None, created_at=wm.created_at)
        service._working_memory_service.list.return_value = [wm]
        message_service.list.return_value = [_make_message("a chuva caiu")]

        _, next_practice = await service.chat(ChatRequest(session_id=1))

        service._working_memory_service.delete.assert_called_once_with(99)
        service._working_memory_service.create.assert_not_called()
        service._chunk_service.get_daily_batch.assert_not_called()
        assert next_practice is None

    async def test_ends_loop_when_no_more_due_chunks(self, mock_language_session_repository):
        service, _, _, message_service, _ = _make_service()
        wm = _make_wm("language:pending", json.dumps({
            "mode": "review", "chunk_id": 42, "track_id": 3, "track_code": "pt",
            "language_name": "Portuguese", "text": "bonjour", "translation": "hello",
            "remaining": 3,
        }))
        wm = WorkingMemoryRead(id=99, key=wm.key, value=wm.value, importance=None,
                               expires_at=None, session_id=None, created_at=wm.created_at)
        service._working_memory_service.list.return_value = [wm]
        service._chunk_service.get_daily_batch.return_value = [_make_batch(3, [_make_chunk(42)])]
        message_service.list.return_value = [_make_message("yes I know it")]

        _, next_practice = await service.chat(ChatRequest(session_id=1))

        service._working_memory_service.delete.assert_called_once_with(99)
        service._working_memory_service.create.assert_not_called()
        assert next_practice is None


def _make_produce_wm(
    remaining: int = 3,
    wm_id: int = 99,
    task_type: str = "sentence",
    chunk_id: int | None = 42,
) -> WorkingMemoryRead:
    return WorkingMemoryRead(
        id=wm_id,
        key="language:pending",
        value=json.dumps({
            "mode": "produce", "chunk_id": chunk_id, "track_id": 3, "track_code": "pt",
            "language_name": "Portuguese", "text": "a chuva caiu", "translation": "it rained",
            "task_type": task_type, "prompt_text": 'Write an original sentence using "a chuva caiu".',
            "remaining": remaining,
        }),
        importance=None, expires_at=None, session_id=None, created_at=datetime(2024, 1, 1),
    )


def _make_production_attempt(score: float = 80.0):
    from app.features.language.production.schemas import ProductionAttemptRead, ProductionGradingRead
    return ProductionAttemptRead(
        session_id=7, track_id=3, chunk_id=42, task_type="sentence", quality_score=3.4,
        grading=ProductionGradingRead(
            score=score, errors=["wrong tense"], corrected_text="A chuva caiu ontem.",
            feedback="Nice attempt!", new_vocabulary=[],
        ),
    )


def _make_production_task(chunk_id: int = 43):
    from app.features.language.production.schemas import ProductionTaskRead
    return ProductionTaskRead(
        track_id=3, track_code="pt", language_name="Portuguese", chunk_id=chunk_id,
        task_type="translate", prompt_text='Translate into Portuguese: "It rained all night."',
        text="outra frase", translation="another phrase", total_due=2,
    )


class TestChatServiceProductionLoop:
    async def test_grades_attempt_with_wm_data_and_user_text(self, mock_language_session_repository):
        service, _, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_produce_wm()]
        service._production_service.grade_attempt = AsyncMock(return_value=_make_production_attempt())
        message_service.list.return_value = [_make_message("A chuva caiu toda a noite")]

        await service.chat(ChatRequest(session_id=1))

        attempt = service._production_service.grade_attempt.call_args[0][0]
        assert attempt.track_id == 3
        assert attempt.chunk_id == 42
        assert attempt.task_type == "sentence"
        assert attempt.prompt_text.startswith("Write an original sentence")
        assert attempt.response_text == "A chuva caiu toda a noite"
        mock_language_session_repository.return_value.get_sessions.assert_not_called()

    async def test_grading_result_appears_in_system_prompt(self, mock_language_session_repository):
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_produce_wm()]
        service._production_service.grade_attempt = AsyncMock(return_value=_make_production_attempt(score=80.0))
        message_service.list.return_value = [_make_message("A chuva caiu toda a noite")]

        await service.chat(ChatRequest(session_id=1))

        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "Production result" in system_prompt
        assert "80/100" in system_prompt
        assert "A chuva caiu ontem." in system_prompt
        assert "wrong tense" in system_prompt

    async def test_advances_to_next_task_when_remaining(self, mock_language_session_repository):
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_produce_wm(remaining=3, wm_id=99)]
        service._production_service.grade_attempt = AsyncMock(return_value=_make_production_attempt())
        service._production_service.get_next_task = AsyncMock(return_value=_make_production_task(chunk_id=43))
        message_service.list.return_value = [_make_message("A chuva caiu toda a noite")]

        _, next_practice = await service.chat(ChatRequest(session_id=1))

        service._production_service.get_next_task.assert_called_once_with(
            3, task_type=None, exclude_chunk_id=42
        )
        service._working_memory_service.delete.assert_called_once_with(99)
        created_value = json.loads(service._working_memory_service.create.call_args[0][0].value)
        assert created_value["mode"] == "produce"
        assert created_value["chunk_id"] == 43
        assert created_value["task_type"] == "translate"
        assert created_value["remaining"] == 2
        assert next_practice is None
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert 'Translate into Portuguese: "It rained all night."' in system_prompt

    async def test_ends_loop_when_remaining_exhausted(self, mock_language_session_repository):
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_produce_wm(remaining=1, wm_id=99)]
        service._production_service.grade_attempt = AsyncMock(return_value=_make_production_attempt())
        message_service.list.return_value = [_make_message("A chuva caiu toda a noite")]

        _, next_practice = await service.chat(ChatRequest(session_id=1))

        service._production_service.get_next_task.assert_not_called()
        service._working_memory_service.delete.assert_called_once_with(99)
        service._working_memory_service.create.assert_not_called()
        assert next_practice is None
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "last exercise" in system_prompt

    async def test_open_ended_loop_keeps_task_type_and_no_chunk(self, mock_language_session_repository):
        from app.features.language.production.schemas import ProductionTaskRead
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [
            _make_produce_wm(remaining=2, wm_id=99, task_type="journal", chunk_id=None)
        ]
        service._production_service.grade_attempt = AsyncMock(return_value=_make_production_attempt())
        journal_task = ProductionTaskRead(
            track_id=3, track_code="pt", language_name="Portuguese", chunk_id=None,
            task_type="journal",
            prompt_text="Write a short journal entry in Portuguese (3-5 sentences) about your plans for tomorrow.",
            text=None, translation=None, total_due=1,
        )
        service._production_service.get_next_task = AsyncMock(return_value=journal_task)
        message_service.list.return_value = [_make_message("Hoje choveu muito e fiquei em casa.")]

        await service.chat(ChatRequest(session_id=1))

        service._production_service.get_next_task.assert_called_once_with(
            3, task_type="journal", exclude_chunk_id=None
        )
        attempt = service._production_service.grade_attempt.call_args[0][0]
        assert attempt.chunk_id is None
        assert attempt.task_type == "journal"
        created_value = json.loads(service._working_memory_service.create.call_args[0][0].value)
        assert created_value["task_type"] == "journal"
        assert created_value["chunk_id"] is None
        assert created_value["remaining"] == 1
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "your plans for tomorrow" in system_prompt

    async def test_spoken_loop_keeps_task_type_and_no_chunk(self, mock_language_session_repository):
        from app.features.language.production.schemas import ProductionTaskRead
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [
            _make_produce_wm(remaining=2, wm_id=99, task_type="speak", chunk_id=None)
        ]
        service._production_service.grade_attempt = AsyncMock(return_value=_make_production_attempt())
        speak_task = ProductionTaskRead(
            track_id=3, track_code="pt", language_name="Portuguese", chunk_id=None,
            task_type="speak",
            prompt_text="Speak for about a minute in Portuguese about your plans for the weekend.",
            text=None, translation=None, total_due=1,
        )
        service._production_service.get_next_task = AsyncMock(return_value=speak_task)
        message_service.list.return_value = [_make_message("Ontem eu fui ao mercado com a minha irmã.")]

        await service.chat(ChatRequest(session_id=1))

        service._production_service.get_next_task.assert_called_once_with(
            3, task_type="speak", exclude_chunk_id=None
        )
        attempt = service._production_service.grade_attempt.call_args[0][0]
        assert attempt.chunk_id is None
        assert attempt.task_type == "speak"
        created_value = json.loads(service._working_memory_service.create.call_args[0][0].value)
        assert created_value["task_type"] == "speak"
        assert created_value["chunk_id"] is None
        assert created_value["remaining"] == 1
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "your plans for the weekend" in system_prompt

    async def test_keeps_wm_when_grading_fails(self, mock_language_session_repository):
        service, llm_provider, _, message_service, _ = _make_service()
        service._working_memory_service.list.return_value = [_make_produce_wm(wm_id=99)]
        service._production_service.grade_attempt = AsyncMock(
            side_effect=HTTPException(status_code=503, detail="LLM down")
        )
        message_service.list.return_value = [_make_message("A chuva caiu toda a noite")]

        _, next_practice = await service.chat(ChatRequest(session_id=1))

        service._working_memory_service.delete.assert_not_called()
        service._working_memory_service.create.assert_not_called()
        assert next_practice is None
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "grading is temporarily unavailable" in system_prompt


class TestChatServiceMemoryExtraction:
    async def test_schedules_extraction_after_chat(self):
        service, _, _, message_service, memory_extraction_service = _make_service()
        msg = _make_message("I prefer dark mode")
        message_service.list.return_value = [msg]
        with patch(
            "app.features.core.chats.service.asyncio.create_task",
            side_effect=lambda coro: coro.close(),
        ) as mock_create_task:
            await service.chat(ChatRequest(session_id=1))
        mock_create_task.assert_called_once()

    async def test_skips_extraction_in_practice_mode(self):
        service, _, _, message_service, memory_extraction_service = _make_service()
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", '{"mode": "practice", "chunk_id": 42, "track_id": 3}')
        ]
        message_service.list.return_value = [_make_message("J'ai un chat")]
        with patch("app.features.core.chats.service.asyncio.create_task") as mock_create_task:
            await service.chat(ChatRequest(session_id=1))
        mock_create_task.assert_not_called()
        memory_extraction_service.extract_and_save.assert_not_called()

    async def test_skips_extraction_in_review_mode(self):
        service, _, _, message_service, memory_extraction_service = _make_service()
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", '{"mode": "review", "chunk_id": 42, "track_id": 3}')
        ]
        message_service.list.return_value = [_make_message("I know this one")]
        with patch("app.features.core.chats.service.asyncio.create_task") as mock_create_task:
            await service.chat(ChatRequest(session_id=1))
        mock_create_task.assert_not_called()
        memory_extraction_service.extract_and_save.assert_not_called()

    async def test_skips_extraction_in_produce_mode(self):
        service, _, _, message_service, memory_extraction_service = _make_service()
        service._working_memory_service.list.return_value = [_make_produce_wm()]
        service._production_service.grade_attempt = AsyncMock(return_value=_make_production_attempt())
        message_service.list.return_value = [_make_message("J'ai un chat")]
        with patch("app.features.core.chats.service.asyncio.create_task") as mock_create_task:
            await service.chat(ChatRequest(session_id=1))
        mock_create_task.assert_not_called()
        memory_extraction_service.extract_and_save.assert_not_called()

    async def test_stream_chat_schedules_extraction(self):
        service, llm_provider, _, message_service, memory_extraction_service = _make_service()

        async def _fake_stream(messages, system=None, meta=None):
            yield "ok"

        llm_provider.stream = _fake_stream
        message_service.list.return_value = [_make_message("I prefer dark mode")]
        with patch(
            "app.features.core.chats.service.asyncio.create_task",
            side_effect=lambda coro: coro.close(),
        ) as mock_create_task:
            async for _ in service.stream_chat(ChatRequest(session_id=1)):
                pass
        mock_create_task.assert_called_once()

    async def test_stream_chat_skips_extraction_when_language_pending(self):
        service, llm_provider, _, message_service, memory_extraction_service = _make_service()

        async def _fake_stream(messages, system=None, meta=None):
            yield "ok"

        llm_provider.stream = _fake_stream
        service._working_memory_service.list.return_value = [
            _make_wm("language:pending", '{"mode": "practice", "chunk_id": 42, "track_id": 3}')
        ]
        message_service.list.return_value = [_make_message("J'ai un chat")]
        with patch("app.features.core.chats.service.asyncio.create_task") as mock_create_task:
            async for _ in service.stream_chat(ChatRequest(session_id=1)):
                pass
        mock_create_task.assert_not_called()
        memory_extraction_service.extract_and_save.assert_not_called()

    async def test_detected_intents_appear_in_system_prompt(self):
        service, llm_provider, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("add event")]
        await service.chat(ChatRequest(session_id=1, detected_intents=["event.add"]))
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "event.add" in system_prompt
        assert "Parallel command pipeline" in system_prompt

    async def test_no_intent_hint_when_not_provided(self):
        service, llm_provider, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "Parallel command pipeline" not in system_prompt


class TestStripMarkdown:
    def test_removes_bold_asterisks(self):
        assert _strip_markdown("Hello **world**") == "Hello world"

    def test_removes_italic_asterisks(self):
        assert _strip_markdown("Hello *world*") == "Hello world"

    def test_removes_italic_underscores(self):
        assert _strip_markdown("Hello _world_") == "Hello world"

    def test_removes_bold_underscores(self):
        assert _strip_markdown("Hello __world__") == "Hello world"

    def test_removes_inline_code(self):
        assert _strip_markdown("Use `print()` to debug") == "Use print() to debug"

    def test_removes_code_block(self):
        assert _strip_markdown("```\ncode here\n```") == ""

    def test_removes_headings(self):
        assert _strip_markdown("## Section title") == "Section title"

    def test_preserves_plain_text(self):
        assert _strip_markdown("Hello, how are you?") == "Hello, how are you?"

    def test_realistic_llm_response(self):
        text = "**Event Name:** Batizado Capoeira\n**Date:** Next Sunday\n**Start Time:** 3:00 PM"
        result = _strip_markdown(text)
        assert "**" not in result
        assert "Batizado Capoeira" in result


class TestToMessageDicts:
    def test_maps_user_message(self):
        messages = [_make_message("hello", role="user")]
        result = _to_message_dicts(messages)
        assert result == [{"role": "user", "content": "hello"}]

    def test_maps_assistant_message(self):
        messages = [_make_message("hi there", role="assistant")]
        result = _to_message_dicts(messages)
        assert result == [{"role": "assistant", "content": "hi there"}]

    def test_preserves_order(self):
        messages = [
            _make_message("question", role="user"),
            _make_message("answer", role="assistant"),
            _make_message("follow-up", role="user"),
        ]
        result = _to_message_dicts(messages)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_empty_list(self):
        assert _to_message_dicts([]) == []
