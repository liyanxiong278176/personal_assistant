"""LLM 客户端测试"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.llm import LLMClient


@pytest.mark.asyncio
async def test_llm_client_requires_api_key():
    """测试 LLM 客户端需要 API key"""
    # 临时移除环境变量
    original_key = os.environ.get("DEEPSEEK_API_KEY")
    os.environ.pop("DEEPSEEK_API_KEY", None)

    client = LLMClient()

    # 无 API key 时应该返回降级消息
    parts = []
    async for chunk in client.stream_chat([{"role": "user", "content": "hi"}]):
        parts.append(chunk)

    result = "".join(parts)
    assert "不可用" in result or "error" in result.lower()

    # 恢复环境变量
    if original_key:
        os.environ["DEEPSEEK_API_KEY"] = original_key


@pytest.mark.asyncio
async def test_llm_client_with_system_prompt():
    """测试带系统提示词的 LLM 客户端"""
    # 这个测试需要真实的 API key，如果没有则跳过
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("需要 DEEPSEEK_API_KEY 环境变量")

    client = LLMClient(api_key=api_key)

    # 测试非流式调用
    result = await client.chat(
        messages=[{"role": "user", "content": "你好"}],
        system_prompt="你是一个旅游助手"
    )

    assert result  # 应该有响应
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_llm_client_stream():
    """测试流式 LLM 客户端"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("需要 DEEPSEEK_API_KEY 环境变量")

    client = LLMClient(api_key=api_key)

    # 测试流式调用
    chunks = []
    async for chunk in client.stream_chat([{"role": "user", "content": "说 '你好'"}]):
        chunks.append(chunk)

    result = "".join(chunks)
    assert result  # 应该有响应
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_llm_client_retry_on_429():
    """测试客户端在 429 错误时重试"""
    client = LLMClient(api_key="test-key", max_retries=2)

    # Mock httpx client
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.aread = AsyncMock(return_value=b"Rate limit exceeded")

    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock()

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_context)

    with patch.object(client, '_get_client', return_value=mock_client):
        chunks = []
        async for chunk in client.stream_chat([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)

        # 第一次失败，重试一次后应该返回错误消息
        result = "".join(chunks)
        assert "429" in result or "API 错误" in result


@pytest.mark.asyncio
async def test_llm_client_max_retries_respected():
    """测试 max_retries 参数被正确使用"""
    client = LLMClient(api_key="test-key", max_retries=1)

    # 验证 max_retries 属性被正确设置
    assert client.max_retries == 1

    client_3 = LLMClient(api_key="test-key", max_retries=3)
    assert client_3.max_retries == 3


@pytest.mark.asyncio
async def test_llm_client_default_max_retries():
    """测试默认 max_retries 为 3"""
    client = LLMClient(api_key="test-key")
    assert client.max_retries == 3
