"""Tests for ToolExecutor retry and fallback strategies."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.tools.executor import ToolExecutor


class TestToolExecutorRetry:
    """Test retry behavior in ToolExecutor."""

    @pytest.mark.asyncio
    async def test_execute_with_retry_success_first_attempt(self):
        """Test that successful execution on first attempt returns success."""
        mock_tool = AsyncMock()
        mock_tool.execute.return_value = {"temp": 25}

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=1)

        assert result["success"] is True
        assert result["data"] == {"temp": 25}
        assert result["retried"] is False
        assert mock_tool.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_success_after_retry(self):
        """Test that retryable error triggers retry and succeeds."""
        mock_tool = AsyncMock()
        # First call fails with timeout, second succeeds
        mock_tool.execute.side_effect = [Exception("timeout"), {"temp": 25}]

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=1)

        assert result["success"] is True
        assert result["data"] == {"temp": 25}
        assert result["retried"] is True
        assert mock_tool.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_with_retry_non_retryable_error(self):
        """Test that non-retryable errors do not trigger retry."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = Exception("Invalid API key")

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=3)

        assert result["success"] is False
        assert "Invalid API key" in result["error"]
        assert result["retried"] == 3
        assert mock_tool.execute.call_count == 1  # No retry for non-retryable

    @pytest.mark.asyncio
    async def test_execute_with_retry_max_attempts_exceeded(self):
        """Test that max retries are respected."""
        mock_tool = AsyncMock()
        # All attempts fail with timeout
        mock_tool.execute.side_effect = [Exception("timeout"), Exception("timeout"), Exception("timeout")]

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=2)

        assert result["success"] is False
        assert "timeout" in result["error"]
        assert mock_tool.execute.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_execute_with_retry_rate_limit_error(self):
        """Test retry on rate limit error (429)."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = [Exception("429 rate limit"), {"temp": 25}]

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=1)

        assert result["success"] is True
        assert result["retried"] is True
        assert mock_tool.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_with_retry_service_unavailable(self):
        """Test retry on 503 Service Unavailable."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = [Exception("503 Service Unavailable"), {"temp": 25}]

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=1)

        assert result["success"] is True
        assert result["retried"] is True

    @pytest.mark.asyncio
    async def test_execute_with_retry_network_error(self):
        """Test retry on network error."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = [Exception("network error"), {"temp": 25}]

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=1)

        assert result["success"] is True
        assert result["retried"] is True

    @pytest.mark.asyncio
    async def test_execute_with_retry_zero_max_retries(self):
        """Test with max_retries=0 (no retries)."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = Exception("timeout")

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_retry("get_weather", city="北京", max_retries=0)

        assert result["success"] is False
        assert result["retried"] == 0
        assert mock_tool.execute.call_count == 1


class TestIsRetryable:
    """Test _is_retryable helper method."""

    def test_is_retryable_timeout(self):
        """Test timeout errors are retryable."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("Request timeout")) is True

    def test_is_retryable_network(self):
        """Test network errors are retryable."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("Network error")) is True
        assert executor._is_retryable(Exception("connection failed")) is True

    def test_is_retryable_rate_limit(self):
        """Test rate limit errors are retryable."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("rate limit exceeded")) is True
        assert executor._is_retryable(Exception("429 Too Many Requests")) is True

    def test_is_retryable_503(self):
        """Test 503 errors are retryable."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("503 Service Unavailable")) is True
        assert executor._is_retryable(Exception("HTTP 503")) is True

    def test_is_retryable_case_insensitive(self):
        """Test retryable check is case insensitive."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("TIMEOUT")) is True
        assert executor._is_retryable(Exception("Network Error")) is True

    def test_is_not_retryable_invalid_api_key(self):
        """Test invalid API key is not retryable."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("Invalid API key")) is False

    def test_is_not_retryable_auth_failed(self):
        """Test authentication failure is not retryable."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("Authentication failed")) is False

    def test_is_not_retryable_bad_request(self):
        """Test bad request is not retryable."""
        executor = ToolExecutor(registry=MagicMock())
        assert executor._is_retryable(Exception("Bad request")) is False


class TestToolExecutorFallback:
    """Test fallback behavior in ToolExecutor."""

    @pytest.mark.asyncio
    async def test_execute_with_fallback_success(self):
        """Test that successful execution does not use cache."""
        mock_tool = AsyncMock()
        mock_tool.execute.return_value = {"temp": 25}

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        mock_cache = MagicMock()
        mock_cache.get.return_value = {"temp": 20}

        executor = ToolExecutor(registry=mock_registry, cache=mock_cache)
        result = await executor.execute_with_fallback("get_weather", city="北京")

        assert result["success"] is True
        assert result["data"] == {"temp": 25}
        assert result["from_cache"] is False

    @pytest.mark.asyncio
    async def test_execute_with_fallback_uses_cache_on_failure(self):
        """Test that cache is used when tool fails."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = Exception("Network timeout")

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        mock_cache = MagicMock()
        mock_cache.get.return_value = {"temp": 20}

        executor = ToolExecutor(registry=mock_registry, cache=mock_cache)
        result = await executor.execute_with_fallback("get_weather", city="北京")

        assert result["from_cache"] is True
        assert result["data"] == {"temp": 20}
        assert result["success"] is True  # Graceful degradation

    @pytest.mark.asyncio
    async def test_execute_with_fallback_no_cache_available(self):
        """Test fallback when no cached value exists."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = Exception("Network timeout")

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        executor = ToolExecutor(registry=mock_registry, cache=mock_cache)
        result = await executor.execute_with_fallback("get_weather", city="北京")

        assert result["success"] is False
        assert result["from_cache"] is False
        assert "Network timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_with_fallback_no_cache_configured(self):
        """Test fallback when no cache is configured."""
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = Exception("Network timeout")

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        executor = ToolExecutor(registry=mock_registry)
        result = await executor.execute_with_fallback("get_weather", city="北京")

        assert result["success"] is False
        assert "Network timeout" in result["error"]
