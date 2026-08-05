from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.http.retry import request_with_retry


class TestRequestWithRetry:
    @pytest.fixture
    def ok_response(self):
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        return response

    @pytest.fixture
    def make_error_response(self):
        def _make(status_code: int) -> MagicMock:
            response = MagicMock()
            response.status_code = status_code
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                str(status_code), request=MagicMock(), response=response
            )
            return response

        return _make

    @pytest.mark.asyncio
    async def test_returns_response_on_first_success(self, ok_response):
        client = MagicMock()
        client.request = AsyncMock(return_value=ok_response)

        result = await request_with_retry(client, "GET", "https://example.com")

        assert result is ok_response
        assert client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_status_then_succeeds(self, make_error_response, ok_response):
        error_response = make_error_response(503)
        client = MagicMock()
        client.request = AsyncMock(side_effect=[error_response, ok_response])

        with patch("app.integrations.http.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await request_with_retry(client, "GET", "https://example.com")

        assert result is ok_response
        assert client.request.call_count == 2
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_retries(self, make_error_response):
        error_response = make_error_response(503)
        client = MagicMock()
        client.request = AsyncMock(return_value=error_response)

        with patch("app.integrations.http.retry.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(httpx.HTTPStatusError):
                await request_with_retry(client, "GET", "https://example.com", max_attempts=3)

        assert client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_on_non_retryable_status(self, make_error_response):
        error_response = make_error_response(400)
        client = MagicMock()
        client.request = AsyncMock(return_value=error_response)

        with pytest.raises(httpx.HTTPStatusError):
            await request_with_retry(client, "GET", "https://example.com")

        assert client.request.call_count == 1
