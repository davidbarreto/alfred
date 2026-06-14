import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.assistant.intents.intent_service import IntentResult, detect_intent


def _make_embedding(content: str = "Add a task to buy groceries"):
    obj = MagicMock()
    obj.source_type = "intent_example"
    obj.source_id = 12345
    obj.content = content
    obj.model = "all-MiniLM-L6-v2"
    obj.dimensions = 384
    obj.embedded_at = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
    return obj


@pytest.fixture()
def mock_provider():
    with patch("app.assistant.intents.intent_service._provider") as p:
        p.embed = AsyncMock(return_value=[0.1] * 384)
        yield p


@pytest.fixture()
def mock_repo():
    with patch("app.assistant.intents.intent_service.EmbeddingRepository") as cls:
        instance = cls.return_value
        yield instance


class TestDetectIntent:
    @pytest.mark.asyncio
    async def test_returns_matching_intent_and_confidence(self, mock_provider, mock_repo):
        embedding = _make_embedding(content="Add a task to buy groceries")
        mock_repo.search = AsyncMock(return_value=[(embedding, 0.92)])

        result = await detect_intent("add groceries task", AsyncMock())

        assert result.intent == "task.add"
        assert result.confidence == 0.92
        assert result.source == "intent_detection"

    @pytest.mark.asyncio
    async def test_confidence_is_rounded_to_4_decimal_places(self, mock_provider, mock_repo):
        embedding = _make_embedding(content="Show me my to-do list")
        mock_repo.search = AsyncMock(return_value=[(embedding, 0.876543210)])

        result = await detect_intent("what are my tasks", AsyncMock())

        assert result.confidence == 0.8765

    @pytest.mark.asyncio
    async def test_returns_unknown_when_no_results(self, mock_provider, mock_repo):
        mock_repo.search = AsyncMock(return_value=[])

        result = await detect_intent("something", AsyncMock())

        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert result.source == "intent_detection"

    @pytest.mark.asyncio
    async def test_returns_unknown_for_unrecognised_content(self, mock_provider, mock_repo):
        embedding = _make_embedding(content="This text is not in INTENT_EXAMPLES")
        mock_repo.search = AsyncMock(return_value=[(embedding, 0.75)])

        result = await detect_intent("something obscure", AsyncMock())

        assert result.intent == "unknown"
        assert result.confidence == 0.75

    @pytest.mark.asyncio
    async def test_source_type_filter_passed_to_repo(self, mock_provider, mock_repo):
        mock_repo.search = AsyncMock(return_value=[])

        await detect_intent("any text", AsyncMock())

        mock_repo.search.assert_called_once()
        call_kwargs = mock_repo.search.call_args.kwargs
        assert call_kwargs["source_types"] == ["intent_example"]
        assert call_kwargs["limit"] == 1
        assert call_kwargs["threshold"] == 0.0

    @pytest.mark.asyncio
    async def test_result_is_intent_result_instance(self, mock_provider, mock_repo):
        embedding = _make_embedding(content="Tell me a joke")
        mock_repo.search = AsyncMock(return_value=[(embedding, 0.55)])

        result = await detect_intent("joke please", AsyncMock())

        assert isinstance(result, IntentResult)
