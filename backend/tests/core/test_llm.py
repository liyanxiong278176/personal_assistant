"""LLM 客户端测试"""

import os
import pytest

from app.core.llm import LLMClient


@pytest.mark.asyncio
async def test_llm_client_requires_api_key():
    """测试 LLM 客户端需要 API key"""
    # 临时移除环境变量
    original_key = os.environ.get("DASHSCOPE_API_KEY")
    os.environ.pop("DASHSCOPE_API_KEY", None)

    client = LLMClient()

    # 无 API key 时应该返回降级消息
    parts = []
    async for chunk in client.stream_chat([{"role": "user", "content": "hi"}]):
        parts.append(chunk)

    result = "".join(parts)
    assert "不可用" in result or "error" in result.lower()

    # 恢复环境变量
    if original_key:
        os.environ["DASHSCOPE_API_KEY"] = original_key


@pytest.mark.asyncio
async def test_llm_client_with_system_prompt():
    """测试带系统提示词的 LLM 客户端"""
    # 这个测试需要真实的 API key，如果没有则跳过
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        pytest.skip("需要 DASHSCOPE_API_KEY 环境变量")

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
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        pytest.skip("需要 DASHSCOPE_API_KEY 环境变量")

    client = LLMClient(api_key=api_key)

    # 测试流式调用
    chunks = []
    async for chunk in client.stream_chat([{"role": "user", "content": "说 '你好'"}]):
        chunks.append(chunk)

    result = "".join(chunks)
    assert result  # 应该有响应
    assert isinstance(result, str)
