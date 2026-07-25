from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.language.conversation.service import ConversationService
from app.shared.audio import AudioConversationResult
from app.shared.llm import LlmResponse

_THREAD_STARTED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _make_track(**kwargs):
    track = MagicMock()
    track.id = kwargs.get("id", 1)
    track.code = kwargs.get("code", "fr")
    track.name = kwargs.get("name", "French")
    return track


def _make_thread(**kwargs):
    thread = MagicMock()
    thread.id = kwargs.get("id", 10)
    thread.track_id = kwargs.get("track_id", 1)
    thread.chat_session_id = kwargs.get("chat_session_id", 5)
    thread.scenario = kwargs.get("scenario", "Ordering coffee")
    thread.voice_reply = kwargs.get("voice_reply", False)
    thread.ended_at = kwargs.get("ended_at", None)
    thread.started_at = kwargs.get("started_at", _THREAD_STARTED_AT)
    return thread


def _make_history_message(role: str, content: str, created_at: datetime | None = None):
    message = MagicMock()
    message.role = role
    message.content = content
    message.created_at = created_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return message


def _make_result(**kwargs) -> AudioConversationResult:
    return AudioConversationResult(
        transcript=kwargs.get("transcript", "Un cafe, s'il vous plait"),
        reply=kwargs.get("reply", "Bien sur! Autre chose?"),
        tip=kwargs.get("tip"),
        raw_response=kwargs.get("raw_response", "{}"),
        tokens_input=kwargs.get("tokens_input", 50),
        tokens_output=kwargs.get("tokens_output", 20),
        tone=kwargs.get("tone"),
    )


def _make_service(**kwargs):
    session = kwargs.get("session") or AsyncMock()
    thread_repo = kwargs.get("thread_repo") or AsyncMock()
    message_service = kwargs.get("message_service") or AsyncMock()
    message_service.create = AsyncMock(return_value=MagicMock(id=99, role="user", content="hi"))
    message_service.list = AsyncMock(return_value=kwargs.get("session_messages", []))
    language_session_service = kwargs.get("language_session_service") or AsyncMock()
    track_repo = kwargs.get("track_repo") or AsyncMock()
    audio_storage = kwargs.get("audio_storage") or AsyncMock()
    audio_converter = kwargs.get("audio_converter") or AsyncMock()
    audio_converter.to_ogg_opus = AsyncMock(return_value=b"ogg-bytes")
    conversation_provider = kwargs.get("conversation_provider") or AsyncMock()
    conversation_provider.provider = "google"
    conversation_provider.model = "gemini-2.5-flash"
    pronunciation_service = kwargs.get("pronunciation_service") or AsyncMock()
    pronunciation_service.get_audio = AsyncMock(return_value=(b"tts-bytes", "audio/ogg"))
    llm_provider = kwargs.get("llm_provider") or AsyncMock()
    llm_provider.provider = "google"
    llm_provider.model = "gemini-2.5-flash"

    service = ConversationService(
        session=session,
        thread_repo=thread_repo,
        message_service=message_service,
        language_session_service=language_session_service,
        track_repo=track_repo,
        audio_storage=audio_storage,
        audio_converter=audio_converter,
        conversation_provider=conversation_provider,
        pronunciation_service=pronunciation_service,
        llm_provider=llm_provider,
    )
    return {
        "service": service,
        "session": session,
        "thread_repo": thread_repo,
        "message_service": message_service,
        "language_session_service": language_session_service,
        "track_repo": track_repo,
        "audio_storage": audio_storage,
        "audio_converter": audio_converter,
        "conversation_provider": conversation_provider,
        "pronunciation_service": pronunciation_service,
        "llm_provider": llm_provider,
    }


class TestStart:
    async def test_creates_thread_and_opening_message(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].create_thread = AsyncMock(return_value=_make_thread())
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Bonjour! Que puis-je vous servir?", tokens_input=10, tokens_output=8)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].start(track_id=1, message_id=42, scenario="Ordering coffee", voice_reply=False)

        parts["thread_repo"].create_thread.assert_awaited_once_with(1, 5, "Ordering coffee", False)
        assert result.opening_text == "Bonjour! Que puis-je vous servir?"
        assert result.opening_audio_ref is None
        parts["pronunciation_service"].get_audio.assert_not_awaited()
        parts["thread_repo"].create_turn.assert_awaited_once()
        create_turn_kwargs = parts["thread_repo"].create_turn.call_args.kwargs
        assert create_turn_kwargs["is_audio"] is False
        assert create_turn_kwargs["audio_ref"] is None

    async def test_voice_reply_synthesizes_opening_audio(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].create_thread = AsyncMock(return_value=_make_thread(voice_reply=True))
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Bonjour!", tokens_input=10, tokens_output=8)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].start(track_id=1, message_id=42, scenario="Ordering coffee", voice_reply=True)

        parts["pronunciation_service"].get_audio.assert_awaited_once_with("Bonjour!", "fr", audio_format="ogg")
        assert result.opening_audio_ref is not None
        parts["audio_storage"].save.assert_awaited_once()


class TestRecordAudioTurn:
    async def test_persists_turn_with_audio_ref_and_tip(self):
        parts = _make_service()
        thread = _make_thread(voice_reply=False)
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply = AsyncMock(
            return_value=_make_result(tip="Watch your 'r' pronunciation")
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()) as mock_log:
            result = await parts["service"].record_audio_turn(thread_id=10, audio=b"raw-audio")

        parts["audio_converter"].to_ogg_opus.assert_awaited_once_with(b"raw-audio")
        assert result.response == "Bien sur! Autre chose?"
        assert result.tip == "Watch your 'r' pronunciation"
        assert result.reply_audio_base64 is None

        # Roleplay always retains the user's audio_ref (unlike free conversation).
        assert parts["audio_storage"].save.await_count == 1
        turn_calls = parts["thread_repo"].create_turn.call_args_list
        assert len(turn_calls) == 2
        user_turn_kwargs = turn_calls[0].kwargs
        assert user_turn_kwargs["is_audio"] is True
        assert user_turn_kwargs["audio_ref"] is not None
        assert user_turn_kwargs["tip"] == "Watch your 'r' pronunciation"

        log_kwargs = mock_log.call_args.kwargs
        assert log_kwargs["is_audio"] is True
        assert log_kwargs["feature"] == "conversation_roleplay"

    async def test_voice_reply_synthesizes_assistant_audio(self):
        parts = _make_service()
        thread = _make_thread(voice_reply=True)
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply = AsyncMock(return_value=_make_result())

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].record_audio_turn(thread_id=10, audio=b"raw-audio")

        assert result.reply_audio_base64 is not None
        parts["pronunciation_service"].get_audio.assert_awaited_once()

    async def test_tone_styles_the_synthesized_reply(self):
        parts = _make_service()
        thread = _make_thread(voice_reply=True)
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply = AsyncMock(
            return_value=_make_result(reply="Bien sur!", tone="cheerful")
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            await parts["service"].record_audio_turn(thread_id=10, audio=b"raw-audio")

        parts["pronunciation_service"].get_audio.assert_awaited_once_with(
            "Say in a cheerful tone: Bien sur!", "fr", audio_format="ogg"
        )

    async def test_missing_thread_raises_404(self):
        from fastapi import HTTPException

        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=None)

        try:
            await parts["service"].record_audio_turn(thread_id=999, audio=b"x")
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 404


class TestEnd:
    async def test_generates_summary_and_records_correction_session(self):
        parts = _make_service(session_messages=[
            _make_history_message("assistant", "Bonjour! Que puis-je vous servir?"),
            _make_history_message("user", "Un cafe"),
        ])
        thread = _make_thread()
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())

        turn = MagicMock()
        turn.tip = "Watch your 'r'"
        message = MagicMock()
        message.role = "user"
        message.content = "Un cafe"
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[(turn, message)])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Great effort! Watch your r sounds.", tokens_input=30, tokens_output=15)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].end(thread_id=10)

        assert result.tip == "Great effort! Watch your r sounds."
        assert result.turn_count == 1
        parts["thread_repo"].end_thread.assert_awaited_once_with(10, "Great effort! Watch your r sounds.")
        parts["language_session_service"].record_session.assert_awaited_once()
        session_create = parts["language_session_service"].record_session.call_args.args[0]
        assert session_create.session_type == "correction"
        assert session_create.transcript_or_notes == "Great effort! Watch your r sounds."

        prompt_text = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "Un cafe" in prompt_text
        assert "Watch your 'r'" in prompt_text

    async def test_no_messages_skips_summary_call(self):
        parts = _make_service(session_messages=[])
        thread = _make_thread()
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])

        result = await parts["service"].end(thread_id=10)

        parts["llm_provider"].complete.assert_not_awaited()
        assert result.tip is None
        assert result.turn_count == 0

    async def test_text_only_turns_still_feed_the_summary(self):
        # No ConversationTurn records at all (the user typed every reply instead of
        # sending audio) — the wrap-up must still see the full exchange via message history.
        parts = _make_service(session_messages=[
            _make_history_message("assistant", "Bonjour! Bienvenue dans notre boulangerie."),
            _make_history_message("user", "Je voudrais un croissant"),
            _make_history_message("assistant", "Bien sur! Ce sera tout?"),
            _make_history_message("user", "Oui, merci"),
        ])
        thread = _make_thread()
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Solid vocabulary! Watch verb agreement.", tokens_input=30, tokens_output=15)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].end(thread_id=10)

        assert result.tip == "Solid vocabulary! Watch verb agreement."
        assert result.turn_count == 2
        prompt_text = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "Je voudrais un croissant" in prompt_text
        assert "Oui, merci" in prompt_text

    async def test_messages_before_thread_started_are_excluded(self):
        parts = _make_service(session_messages=[
            _make_history_message("user", "unrelated earlier chat", created_at=datetime(2019, 1, 1, tzinfo=timezone.utc)),
            _make_history_message("user", "Un cafe", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ])
        thread = _make_thread(started_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Nice work.", tokens_input=10, tokens_output=5)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].end(thread_id=10)

        assert result.turn_count == 1
        prompt_text = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "unrelated earlier chat" not in prompt_text
        assert "Un cafe" in prompt_text
