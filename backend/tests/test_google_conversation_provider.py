import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.google.conversation_provider import GoogleConversationProvider


def _mock_response(payload: dict, tokens_input: int = 100, tokens_output: int = 50) -> MagicMock:
    resp = MagicMock()
    resp.text = json.dumps(payload)
    resp.usage_metadata.prompt_token_count = tokens_input
    resp.usage_metadata.candidates_token_count = tokens_output
    return resp


class TestProviderIdentity:
    def test_exposes_provider_and_model(self):
        provider = GoogleConversationProvider(api_key="test-key", model_name="gemini-2.5-flash")
        assert provider.provider == "google"
        assert provider.model == "gemini-2.5-flash"


class TestReply:
    @pytest.mark.asyncio
    async def test_parses_structured_json_response(self):
        payload = {"transcript": "Un cafe", "reply": "Bien sur!", "tip": "Watch your accent"}
        with patch("app.integrations.google.conversation_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_response(payload))
            mock_client_cls.return_value = mock_client

            provider = GoogleConversationProvider(api_key="test-key", model_name="gemini-2.5-flash")
            result = await provider.reply(
                history=[{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Salut!"}],
                current_audio=b"fake-audio",
                mime_type="audio/ogg",
                system="Roleplay a cafe scene.",
            )

        assert result.transcript == "Un cafe"
        assert result.reply == "Bien sur!"
        assert result.tip == "Watch your accent"
        assert result.tokens_input == 100
        assert result.tokens_output == 50
        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash"
        contents = call_kwargs["contents"]
        # Only the final turn carries audio; history stays plain text.
        assert contents[-1].role == "user"
        assert contents[-1].parts[0].inline_data.mime_type == "audio/ogg"
        assert contents[-1].parts[0].inline_data.data == b"fake-audio"
        assert contents[0].parts[0].text == "Bonjour"

    @pytest.mark.asyncio
    async def test_null_tip_becomes_none(self):
        payload = {"transcript": "hi", "reply": "hello", "tip": None}
        with patch("app.integrations.google.conversation_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_response(payload))
            mock_client_cls.return_value = mock_client

            provider = GoogleConversationProvider(api_key="test-key", model_name="gemini-2.5-flash")
            result = await provider.reply(history=[], current_audio=b"x", mime_type="audio/ogg", system="sys")

        assert result.tip is None

    @pytest.mark.asyncio
    async def test_strips_markdown_code_fences(self):
        payload = {"transcript": "hi", "reply": "hello", "tip": None}
        with patch("app.integrations.google.conversation_provider.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            resp = MagicMock()
            resp.text = f"```json\n{json.dumps(payload)}\n```"
            resp.usage_metadata = None
            mock_client.aio.models.generate_content = AsyncMock(return_value=resp)
            mock_client_cls.return_value = mock_client

            provider = GoogleConversationProvider(api_key="test-key", model_name="gemini-2.5-flash")
            result = await provider.reply(history=[], current_audio=b"x", mime_type="audio/ogg", system="sys")

        assert result.reply == "hello"
        assert result.tokens_input is None
