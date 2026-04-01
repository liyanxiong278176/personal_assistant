"""LLM 客户端封装

封装通义千问 API 调用，提供流式和非流式接口。
"""

import json
import logging
import os
from typing import AsyncIterator, Optional, List, Dict

import httpx

from ..errors import AgentError, DegradationLevel, DegradationStrategy

logger = logging.getLogger(__name__)

# DashScope API endpoint
DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


class LLMClient:
    """LLM 客户端

    封装通义千问 API，提供重试和降级能力。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen-plus",
        max_retries: int = 3,
        timeout: float = 60.0
    ):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            logger.warning("[LLMClient] No API key provided")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTPX async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """流式聊天

        Args:
            messages: 消息列表
            system_prompt: 系统提示词（可选）

        Yields:
            str: 流式响应片段
        """
        if not self.api_key:
            yield DegradationStrategy.get_message(DegradationLevel.LLM_DEGRADED)
            return

        # 构建完整消息列表
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        try:
            client = await self._get_client()

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": full_messages,
                "stream": True
            }

            async with client.stream(
                "POST",
                DASHSCOPE_API_URL,
                headers=headers,
                json=payload
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"[LLMClient] API error: {response.status_code} - {error_text}")
                    yield f"API 错误: {response.status_code}"
                    return

                # 处理 SSE 流
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    data = line[5:].strip()  # 移除 "data:" 前缀

                    if data == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data)
                        content = self._extract_content(chunk_data)
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        logger.debug(f"[LLMClient] Failed to parse chunk: {data}")
                        continue

        except httpx.TimeoutException:
            logger.error(f"[LLMClient] Request timeout after {self.timeout}s")
            raise AgentError(f"LLM 请求超时")
        except Exception as e:
            logger.error(f"[LLMClient] Error: {e}")
            raise AgentError(f"LLM 调用失败: {e}")

    def _extract_content(self, chunk_data: dict) -> str:
        """从 DashScope 流式响应块中提取内容"""
        try:
            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
            return delta.get("content", "")
        except (KeyError, IndexError, TypeError):
            return ""

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """非流式聊天

        Args:
            messages: 消息列表
            system_prompt: 系统提示词（可选）

        Returns:
            str: 完整响应
        """
        parts = []
        async for chunk in self.stream_chat(messages, system_prompt):
            parts.append(chunk)
        return "".join(parts)
