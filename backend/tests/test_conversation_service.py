import base64
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.language.conversation.service import ConversationService
from app.shared.conversation import ConversationTurnResult
from app.shared.llm import LlmResponse

_THREAD_STARTED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _summary_json(summary: str = "Great effort!", new_vocabulary: list | None = None) -> str:
    return json.dumps({"summary": summary, "new_vocabulary": new_vocabulary or []})


def _make_track(**kwargs):
    track = MagicMock()
    track.id = kwargs.get("id", 1)
    track.code = kwargs.get("code", "fr")
    track.name = kwargs.get("name", "French")
    track.level = kwargs.get("level", "A1")
    return track


def _make_thread(**kwargs):
    thread = MagicMock()
    thread.id = kwargs.get("id", 10)
    thread.track_id = kwargs.get("track_id", 1)
    thread.chat_session_id = kwargs.get("chat_session_id", 5)
    thread.mode = kwargs.get("mode", "roleplay")
    thread.scenario = kwargs.get("scenario", "Ordering coffee")
    thread.voice_reply = kwargs.get("voice_reply", False)
    thread.level_override = kwargs.get("level_override", None)
    thread.ended_at = kwargs.get("ended_at", None)
    thread.started_at = kwargs.get("started_at", _THREAD_STARTED_AT)
    return thread


def _make_history_message(role: str, content: str, created_at: datetime | None = None):
    message = MagicMock()
    message.role = role
    message.content = content
    message.created_at = created_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return message


def _make_result(**kwargs) -> ConversationTurnResult:
    return ConversationTurnResult(
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
    chunk_service = kwargs.get("chunk_service") or AsyncMock()
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
        chunk_service=chunk_service,
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
        "chunk_service": chunk_service,
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
            result = await parts["service"].start(track_id=1, message_id=42, mode="roleplay", scenario="Ordering coffee", voice_reply=False)

        parts["thread_repo"].create_thread.assert_awaited_once_with(
            1, 5, "roleplay", "Ordering coffee", False, None
        )
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
            result = await parts["service"].start(track_id=1, message_id=42, mode="roleplay", scenario="Ordering coffee", voice_reply=True)

        parts["pronunciation_service"].get_audio.assert_awaited_once_with(
            "Say exactly as written: Bonjour!", "fr", audio_format="ogg"
        )
        assert result.opening_audio_ref is not None
        assert result.opening_audio_base64 == base64.b64encode(b"tts-bytes").decode("ascii")
        parts["audio_storage"].save.assert_awaited_once()
        create_turn_kwargs = parts["thread_repo"].create_turn.call_args.kwargs
        assert create_turn_kwargs["is_audio"] is True


    async def test_free_conversation_opens_without_a_line(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].create_thread = AsyncMock(
            return_value=_make_thread(mode="conversation", scenario=None)
        )
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))

        result = await parts["service"].start(
            track_id=1, message_id=42, mode="conversation", scenario=None, voice_reply=True
        )

        # Free conversation waits for David to speak first — no opener, no LLM call, no turn.
        parts["thread_repo"].create_thread.assert_awaited_once_with(
            1, 5, "conversation", None, True, None
        )
        assert result.opening_text is None
        assert result.opening_audio_ref is None
        parts["llm_provider"].complete.assert_not_awaited()
        parts["thread_repo"].create_turn.assert_not_awaited()

    async def test_free_conversation_at_a0_gets_a_beginner_opening(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].create_thread = AsyncMock(
            return_value=_make_thread(mode="conversation", scenario="food", level_override="A0", voice_reply=True)
        )
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Let's practice! Try saying 'Bonjour' (Hello).", tokens_input=10, tokens_output=8)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].start(
                track_id=1, message_id=42, mode="conversation", scenario="food",
                voice_reply=True, level_override="A0",
            )

        opening_prompt = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "total beginner" in opening_prompt
        assert "Topic: food." in opening_prompt
        assert result.opening_text == "Let's practice! Try saying 'Bonjour' (Hello)."
        assert result.opening_audio_base64 == base64.b64encode(b"tts-bytes").decode("ascii")
        parts["thread_repo"].create_turn.assert_awaited_once()

    async def test_free_conversation_at_a0_falls_back_to_track_level(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track(level="A0"))
        parts["thread_repo"].create_thread = AsyncMock(
            return_value=_make_thread(mode="conversation", scenario=None)
        )
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Let's get started!", tokens_input=10, tokens_output=8)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].start(
                track_id=1, message_id=42, mode="conversation", scenario=None, voice_reply=False,
            )

        opening_prompt = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "No set topic" in opening_prompt
        assert result.opening_text == "Let's get started!"

    async def test_free_conversation_at_a1_still_opens_without_a_line(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track(level="A1"))
        parts["thread_repo"].create_thread = AsyncMock(
            return_value=_make_thread(mode="conversation", scenario=None)
        )
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))

        result = await parts["service"].start(
            track_id=1, message_id=42, mode="conversation", scenario=None, voice_reply=False,
        )

        assert result.opening_text is None
        parts["llm_provider"].complete.assert_not_awaited()

    async def test_level_override_passed_through_to_create_thread(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].create_thread = AsyncMock(return_value=_make_thread(level_override="A0"))
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Bonjour!", tokens_input=10, tokens_output=8)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            await parts["service"].start(
                track_id=1, message_id=42, mode="roleplay", scenario="Ordering coffee",
                voice_reply=False, level_override="A0",
            )

        parts["thread_repo"].create_thread.assert_awaited_once_with(
            1, 5, "roleplay", "Ordering coffee", False, "A0"
        )
        opening_prompt = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "A0" in opening_prompt

    async def test_no_level_override_falls_back_to_track_level(self):
        parts = _make_service()
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track(level="B2"))
        parts["thread_repo"].create_thread = AsyncMock(return_value=_make_thread())
        parts["message_service"].get = AsyncMock(return_value=MagicMock(session_id=5))
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Bonjour!", tokens_input=10, tokens_output=8)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            await parts["service"].start(
                track_id=1, message_id=42, mode="roleplay", scenario="Ordering coffee", voice_reply=False,
            )

        opening_prompt = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "B2" in opening_prompt


class TestRecordAudioTurn:
    async def test_persists_turn_with_audio_ref_and_tip(self):
        parts = _make_service()
        thread = _make_thread(voice_reply=False)
        parts["thread_repo"].get_thread = AsyncMock(return_value=thread)
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply_audio = AsyncMock(
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
        parts["conversation_provider"].reply_audio = AsyncMock(return_value=_make_result())

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
        parts["conversation_provider"].reply_audio = AsyncMock(
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




def _make_turn(role: str, content: str, tip: str | None = None):
    turn = MagicMock()
    turn.tip = tip
    message = MagicMock()
    message.role = role
    message.content = content
    return turn, message


class TestRecordTextTurn:
    async def test_persists_turn_without_audio(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=_make_thread(voice_reply=False))
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply_text = AsyncMock(
            return_value=_make_result(transcript="Un cafe", tip="Watch the article")
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()) as mock_log:
            result = await parts["service"].record_text_turn(thread_id=10, text="Un cafe")

        parts["conversation_provider"].reply_text.assert_awaited_once()
        assert parts["conversation_provider"].reply_text.call_args.args[1] == "Un cafe"
        # No transcription and no audio blob to keep for a typed turn.
        parts["audio_converter"].to_ogg_opus.assert_not_awaited()
        parts["audio_storage"].save.assert_not_awaited()

        assert result.response == "Bien sur! Autre chose?"
        assert result.tip == "Watch the article"
        assert result.reply_audio_base64 is None

        turn_calls = parts["thread_repo"].create_turn.call_args_list
        assert len(turn_calls) == 2
        user_turn_kwargs = turn_calls[0].kwargs
        assert user_turn_kwargs["is_audio"] is False
        assert user_turn_kwargs["audio_ref"] is None
        assert user_turn_kwargs["tip"] == "Watch the article"
        assert mock_log.call_args.kwargs["is_audio"] is False

    async def test_voice_reply_still_synthesizes_for_a_typed_turn(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=_make_thread(voice_reply=True))
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply_text = AsyncMock(return_value=_make_result())

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].record_text_turn(thread_id=10, text="Un cafe")

        assert result.reply_audio_base64 is not None
        parts["pronunciation_service"].get_audio.assert_awaited_once()

    async def test_free_conversation_uses_the_conversation_prompt(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(
            return_value=_make_thread(mode="conversation", scenario="food")
        )
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply_text = AsyncMock(return_value=_make_result())

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()) as mock_log:
            await parts["service"].record_text_turn(thread_id=10, text="J'aime le fromage")

        system_prompt = parts["conversation_provider"].reply_text.call_args.args[2]
        assert "free-flowing conversation" in system_prompt
        assert "Talk about: food." in system_prompt
        assert mock_log.call_args.kwargs["feature"] == "conversation_conversation"

    async def test_turn_prompt_uses_thread_level_override_not_track_level(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(
            return_value=_make_thread(mode="conversation", scenario="food", level_override="A0")
        )
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track(level="C1"))
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])
        parts["conversation_provider"].reply_text = AsyncMock(return_value=_make_result())

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            await parts["service"].record_text_turn(thread_id=10, text="J'aime le fromage")

        system_prompt = parts["conversation_provider"].reply_text.call_args.args[2]
        assert "A0" in system_prompt
        assert "C1" not in system_prompt

    async def test_ended_thread_raises_404(self):
        from fastapi import HTTPException

        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(
            return_value=_make_thread(ended_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )

        try:
            await parts["service"].record_text_turn(thread_id=10, text="hi")
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 404


class TestEnd:
    async def test_generates_summary_and_records_correction_session(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=_make_thread())
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[
            _make_turn("assistant", "Bonjour! Que puis-je vous servir?"),
            _make_turn("user", "Un cafe", tip="Watch your 'r'"),
        ])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(
                text=_summary_json("Great effort! Watch your r sounds."), tokens_input=30, tokens_output=15
            )
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].end(thread_id=10)

        assert result.tip == "Great effort! Watch your r sounds."
        assert result.turn_count == 1
        parts["thread_repo"].end_thread.assert_awaited_once_with(10, "Great effort! Watch your r sounds.")
        session_create = parts["language_session_service"].record_session.call_args.args[0]
        assert session_create.session_type == "correction"
        assert session_create.transcript_or_notes == "Great effort! Watch your r sounds."

        prompt_text = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "Un cafe" in prompt_text
        assert "Watch your 'r'" in prompt_text
        assert "Ordering coffee" in prompt_text

    async def test_text_turns_feed_the_summary(self):
        # A fully typed roleplay: every turn is still a tracked ConversationTurn, so the
        # wrap-up sees the whole exchange rather than just the opening line.
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=_make_thread())
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[
            _make_turn("assistant", "Bonjour! Bienvenue dans notre boulangerie."),
            _make_turn("user", "Je voudrais un croissant"),
            _make_turn("assistant", "Bien sur! Ce sera tout?"),
            _make_turn("user", "Oui, merci"),
        ])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text=_summary_json("Solid vocabulary!"), tokens_input=30, tokens_output=15)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].end(thread_id=10)

        assert result.turn_count == 2
        prompt_text = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "Je voudrais un croissant" in prompt_text
        assert "Oui, merci" in prompt_text

    async def test_free_conversation_also_gets_end_feedback(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(
            return_value=_make_thread(mode="conversation", scenario="guitars")
        )
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[
            _make_turn("user", "J'aime la guitare", tip="Verb agreement"),
        ])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(
                text=_summary_json("Nice chat! Watch agreement."), tokens_input=30, tokens_output=15
            )
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].end(thread_id=10)

        assert result.tip == "Nice chat! Watch agreement."
        prompt_text = parts["llm_provider"].complete.call_args.args[0][0]["content"]
        assert "free conversation practice session" in prompt_text
        assert "Topic: guitars" in prompt_text
        assert "J'aime la guitare" in prompt_text

    async def test_queues_vocabulary_candidates_from_summary(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=_make_thread())
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[
            _make_turn("user", "Je vou au marché", tip="Should be 'Je vais au marché'"),
        ])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(
                text=_summary_json("Watch your verb conjugation.", [
                    {"text": "je vais", "translation": "I go", "cefr_level": "A1"},
                ]),
                tokens_input=30, tokens_output=15,
            )
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            await parts["service"].end(thread_id=10)

        parts["chunk_service"].queue_vocabulary_candidates.assert_awaited_once()
        call_args = parts["chunk_service"].queue_vocabulary_candidates.call_args.args
        assert call_args[0] == 1
        assert call_args[1][0].text == "je vais"
        assert call_args[1][0].cefr_level == "A1"

    async def test_malformed_summary_json_falls_back_to_raw_text(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=_make_thread())
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[
            _make_turn("user", "Un cafe"),
        ])
        parts["llm_provider"].complete = AsyncMock(
            return_value=LlmResponse(text="Not JSON at all, just a nice note.", tokens_input=30, tokens_output=15)
        )

        with patch("app.features.language.conversation.service.create_llm_call", AsyncMock()):
            result = await parts["service"].end(thread_id=10)

        assert result.tip == "Not JSON at all, just a nice note."
        parts["chunk_service"].queue_vocabulary_candidates.assert_not_awaited()

    async def test_no_turns_skips_summary_call(self):
        parts = _make_service()
        parts["thread_repo"].get_thread = AsyncMock(return_value=_make_thread())
        parts["track_repo"].get_track = AsyncMock(return_value=_make_track())
        parts["thread_repo"].get_turns_with_messages = AsyncMock(return_value=[])

        result = await parts["service"].end(thread_id=10)

        parts["llm_provider"].complete.assert_not_awaited()
        assert result.tip is None
        assert result.turn_count == 0
