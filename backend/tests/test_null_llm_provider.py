import pytest

from app.integrations.null.llm_provider import NullLlmProvider


class TestNullLlmProvider:

    @pytest.mark.asyncio
    async def test_complete_returns_canned_response(self):
        provider = NullLlmProvider()

        result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.text
        assert result.finish_reason == "STOP"
        assert result.tokens_input == 0
        assert result.tokens_output == 0

    @pytest.mark.asyncio
    async def test_stream_yields_canned_text_and_sets_finish_reason(self):
        from app.shared.llm import StreamMeta

        provider = NullLlmProvider()
        meta = StreamMeta()

        chunks = [chunk async for chunk in provider.stream([{"role": "user", "content": "hi"}], meta=meta)]

        assert "".join(chunks)
        assert meta.finish_reason == "STOP"
        assert meta.truncated is False

    def test_exposes_provider_and_model_name(self):
        provider = NullLlmProvider()

        assert provider.provider == "null"
        assert provider.model == "null"
