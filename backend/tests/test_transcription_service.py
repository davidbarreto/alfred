from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.core.transcription.service import TranscriptionService
from app.shared.audio import TranscriptionResult


def _make_service(**kwargs):
    session = kwargs.get("session") or AsyncMock()
    provider = kwargs.get("provider") or AsyncMock()
    provider.provider = "google"
    provider.model = "gemini-2.5-flash"
    provider.transcribe.return_value = kwargs.get(
        "result",
        TranscriptionResult(text="hello there", tokens_input=100, tokens_output=50, finish_reason="STOP"),
    )
    service = TranscriptionService(provider=provider, session=session)
    return service, session, provider


def _patch_family_contacts(names: list[str]):
    contacts = [MagicMock(name=n) for n in names]
    for contact, n in zip(contacts, names):
        contact.name = n
    repo = MagicMock()
    repo.get_contacts = AsyncMock(return_value=contacts)
    return patch("app.features.core.transcription.service.ContactRepository", return_value=repo)


class TestTranscribe:

    @pytest.mark.asyncio
    async def test_transcribes_and_logs_llm_call(self):
        service, session, provider = _make_service()

        with _patch_family_contacts([]), patch(
            "app.features.core.transcription.service.create_llm_call", AsyncMock()
        ) as mock_log:
            result = await service.transcribe(b"raw-audio", "audio/ogg")

        provider.transcribe.assert_awaited_once()
        call_args = provider.transcribe.call_args
        assert call_args.args == (b"raw-audio", "audio/ogg")
        assert "commands the speaker may start with" in call_args.kwargs["context"]
        assert result.text == "hello there"

        mock_log.assert_awaited_once()
        log_call = mock_log.call_args
        assert log_call.args[0] is session
        assert log_call.kwargs["provider"] == "google"
        assert log_call.kwargs["model"] == "gemini-2.5-flash"
        assert log_call.kwargs["feature"] == "transcription"
        assert log_call.kwargs["response"] == "hello there"
        assert log_call.kwargs["tokens_input"] == 100
        assert log_call.kwargs["tokens_output"] == 50
        assert log_call.kwargs["finish_reason"] == "STOP"
        assert log_call.kwargs["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_context_includes_family_contact_names(self):
        service, session, provider = _make_service()

        with _patch_family_contacts(["Kenai", "Maria"]), patch(
            "app.features.core.transcription.service.create_llm_call", AsyncMock()
        ):
            await service.transcribe(b"raw-audio", "audio/ogg")

        context = provider.transcribe.call_args.kwargs["context"]
        assert "Kenai" in context
        assert "Maria" in context

    @pytest.mark.asyncio
    async def test_context_omits_family_hint_when_no_family_contacts(self):
        service, session, provider = _make_service()

        with _patch_family_contacts([]), patch(
            "app.features.core.transcription.service.create_llm_call", AsyncMock()
        ):
            await service.transcribe(b"raw-audio", "audio/ogg")

        context = provider.transcribe.call_args.kwargs["context"]
        assert "Family member names" not in context
