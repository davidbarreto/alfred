from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_conversation_service
from app.features.language.conversation.schemas import (
    ConversationStartRead,
    ConversationThreadRead,
    ConversationTurnRead,
)

AUTH = {"Authorization": "Bearer test-api-token"}
_NOW = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def client():
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[get_conversation_service] = lambda: service
    with TestClient(app) as c:
        yield c, service
    app.dependency_overrides.clear()


def _thread(**kwargs) -> ConversationThreadRead:
    return ConversationThreadRead(
        id=kwargs.get("id", 1),
        track_id=kwargs.get("track_id", 3),
        chat_session_id=kwargs.get("chat_session_id", 5),
        mode=kwargs.get("mode", "roleplay"),
        scenario=kwargs.get("scenario", "Ordering coffee"),
        voice_reply=kwargs.get("voice_reply", False),
        level_override=kwargs.get("level_override"),
        started_at=_NOW,
        ended_at=kwargs.get("ended_at"),
        tip=kwargs.get("tip"),
    )


def _StartRead(**kwargs) -> ConversationStartRead:
    return ConversationStartRead(
        thread_id=kwargs.get("thread_id", 1),
        track_code=kwargs.get("track_code", "fr"),
        language_name=kwargs.get("language_name", "French"),
        opening_text=kwargs.get("opening_text"),
        opening_audio_ref=kwargs.get("opening_audio_ref"),
    )


def _turn(**kwargs) -> ConversationTurnRead:
    return ConversationTurnRead(
        id=kwargs.get("id", 1),
        thread_id=kwargs.get("thread_id", 1),
        message_id=kwargs.get("message_id", 10),
        role=kwargs.get("role", "user"),
        content=kwargs.get("content", "Un cafe"),
        is_audio=kwargs.get("is_audio", False),
        audio_ref=kwargs.get("audio_ref"),
        tip=kwargs.get("tip"),
        created_at=_NOW,
    )


class TestGetThreads:
    def test_returns_threads(self, client):
        c, service = client
        service.get_threads.return_value = [_thread(tip="Nice work")]

        resp = c.get("/language/conversation/threads", headers=AUTH)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["mode"] == "roleplay"
        assert body[0]["scenario"] == "Ordering coffee"
        assert body[0]["tip"] == "Nice work"

    def test_passes_filters_through(self, client):
        c, service = client
        service.get_threads.return_value = []

        resp = c.get(
            "/language/conversation/threads?track_id=3&mode=conversation&active_only=true&limit=5&offset=10",
            headers=AUTH,
        )

        assert resp.status_code == 200
        filters = service.get_threads.call_args.args[0]
        assert filters.track_id == 3
        assert filters.mode == "conversation"
        assert filters.active_only is True
        assert filters.limit == 5
        assert filters.offset == 10

    def test_rejects_unknown_mode(self, client):
        c, _ = client
        assert c.get("/language/conversation/threads?mode=bogus", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        c, _ = client
        # No bearer header at all — FastAPI's security dependency rejects with 403.
        assert c.get("/language/conversation/threads").status_code == 403


class TestStartConversation:
    def test_passes_level_override_through_to_service(self, client):
        c, service = client
        service.start.return_value = _StartRead(thread_id=5, track_code="fr", language_name="French")

        resp = c.post(
            "/language/conversation/start",
            headers=AUTH,
            json={
                "track_id": 3, "message_id": 1, "mode": "roleplay",
                "scenario": "Ordering coffee", "voice_reply": False, "level_override": "A0",
            },
        )

        assert resp.status_code == 201
        service.start.assert_awaited_once_with(3, 1, "roleplay", "Ordering coffee", False, level_override="A0")

    def test_level_override_defaults_to_none(self, client):
        c, service = client
        service.start.return_value = _StartRead(thread_id=5, track_code="fr", language_name="French")

        resp = c.post(
            "/language/conversation/start",
            headers=AUTH,
            json={"track_id": 3, "message_id": 1, "mode": "roleplay", "scenario": "Ordering coffee"},
        )

        assert resp.status_code == 201
        assert service.start.call_args.kwargs["level_override"] is None


class TestGetThreadTurns:
    def test_returns_turns_with_message_text_and_tips(self, client):
        c, service = client
        service.get_thread_turns.return_value = [
            _turn(id=1, role="assistant", content="Bonjour!"),
            _turn(id=2, role="user", content="Un cafe", is_audio=True, tip="Watch your 'r'"),
        ]

        resp = c.get("/language/conversation/threads/1/turns", headers=AUTH)

        assert resp.status_code == 200
        body = resp.json()
        assert [t["role"] for t in body] == ["assistant", "user"]
        assert body[1]["content"] == "Un cafe"
        assert body[1]["is_audio"] is True
        assert body[1]["tip"] == "Watch your 'r'"
        service.get_thread_turns.assert_awaited_once_with(1)

    def test_propagates_404_for_missing_thread(self, client):
        from fastapi import HTTPException

        c, service = client
        service.get_thread_turns.side_effect = HTTPException(status_code=404, detail="not found")

        assert c.get("/language/conversation/threads/999/turns", headers=AUTH).status_code == 404
