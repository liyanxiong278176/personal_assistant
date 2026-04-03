"""LLM 客户端封装

封装 DeepSeek API 调用，提供流式和非流式接口。
支持 Function Calling（工具调用）功能。
"""

import asyncio
import json
import logging
import os
from typing import AsyncIterator, Optional, List, Dict, Any, Union

import httpx

from ..errors import AgentError, DegradationLevel, DegradationStrategy

logger = logging.getLogger(__name__)

# DeepSeek API endpoint (OpenAI compatible)
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


class ToolCall:
    """工具调用请求

    表示 LLM 请求调用某个工具。
    """
    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments

    def __repr__(self):
        return f"ToolCall(id={self.id!r}, name={self.name!r}, args={self.arguments})"


class LLMClient:
    """LLM 客户端

    封装 DeepSeek API，提供重试和降级能力。
    支持 Function Calling（工具调用）功能。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
        max_retries: int = 3,
        timeout: float = 60.0
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
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

    def _format_tools_for_api(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将工具定义格式化为 API 格式

        Args:
            tools: 工具定义列表，每个包含 name, description, parameters

        Returns:
            API 格式的工具列表
        """
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            })
        return formatted

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

        # 重试逻辑
        last_error = None
        for attempt in range(self.max_retries):
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
                    DEEPSEEK_API_URL,
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(
                            f"[LLMClient] API error: {response.status_code} - {error_text}"
                        )

                        # 可重试的状态码: 429 (rate limit), 500+, 503, 504
                        if response.status_code in (429, 500, 502, 503, 504):
                            if attempt < self.max_retries - 1:
                                delay = 2 ** attempt  # 指数退避: 1s, 2s, 4s...
                                logger.warning(
                                    f"[LLMClient] Retryable error {response.status_code}, "
                                    f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})"
                                )
                                await asyncio.sleep(delay)
                                last_error = f"API error: {response.status_code}"
                                continue

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

                    # 成功完成，退出重试循环
                    return

            except httpx.TimeoutException as e:
                logger.error(f"[LLMClient] Request timeout after {self.timeout}s")
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        f"[LLMClient] Timeout, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    last_error = str(e)
                    continue
                raise AgentError(f"LLM 请求超时")

            except httpx.HTTPStatusError as e:
                logger.error(f"[LLMClient] HTTP status error: {e.response.status_code}")
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        f"[LLMClient] HTTP error, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    last_error = str(e)
                    continue
                raise AgentError(f"LLM HTTP 错误: {e}")

            except httpx.NetworkError as e:
                logger.error(f"[LLMClient] Network error: {e}")
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        f"[LLMClient] Network error, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    last_error = str(e)
                    continue
                raise AgentError(f"LLM 网络错误: {e}")

            except Exception as e:
                logger.error(f"[LLMClient] Unexpected error: {e}")
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        f"[LLMClient] Unexpected error, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    last_error = str(e)
                    continue
                raise AgentError(f"LLM 调用失败: {e}")

        # 所有重试都失败后
        if last_error:
            logger.error(f"[LLMClient] All {self.max_retries} retries failed: {last_error}")
            raise AgentError(f"LLM 调用失败（已重试 {self.max_retries} 次）: {last_error}")

    def _extract_content(self, chunk_data: dict) -> str:
        """从 DeepSeek 流式响应块中提取内容"""
        try:
            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
            return delta.get("content", "")
        except (KeyError, IndexError, TypeError):
            return ""

    def _extract_tool_calls(self, chunk_data: dict) -> List[ToolCall]:
        """从响应块中提取工具调用"""
        try:
            choice = chunk_data.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            tool_calls_delta = delta.get("tool_calls", [])

            tool_calls = []
            for tc in tool_calls_delta:
                # 工具调用可能在流式响应中分块到达
                call_id = tc.get("id", "")
                function = tc.get("function", {})
                name = function.get("name", "")
                arguments_str = function.get("arguments", "{}")

                # 解析参数（流式情况下可能不完整）
                try:
                    arguments = json.loads(arguments_str) if arguments_str else {}
                except json.JSONDecodeError:
                    arguments = {"_raw": arguments_str}

                if name:  # 只有有名称时才添加
                    tool_calls.append(ToolCall(
                        id=call_id,
                        name=name,
                        arguments=arguments
                    ))
            return tool_calls
        except (KeyError, IndexError, TypeError):
            return []

    async def stream_chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[Union[str, ToolCall]]:
        """支持工具调用的流式聊天

        Args:
            messages: 消息列表
            tools: 工具定义列表，每个包含 name, description, parameters
            system_prompt: 系统提示词（可选）

        Yields:
            Union[str, ToolCall]: 流式响应片段或工具调用
        """
        if not self.api_key:
            yield DegradationStrategy.get_message(DegradationLevel.LLM_DEGRADED)
            return

        # 构建完整消息列表
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # 格式化工具定义
        formatted_tools = self._format_tools_for_api(tools)

        # 重试逻辑
        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = await self._get_client()

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "model": self.model,
                    "messages": full_messages,
                    "tools": formatted_tools,
                    "stream": True
                }

                async with client.stream(
                    "POST",
                    DEEPSEEK_API_URL,
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(
                            f"[LLMClient] API error: {response.status_code} - {error_text}"
                        )

                        if response.status_code in (429, 500, 502, 503, 504):
                            if attempt < self.max_retries - 1:
                                delay = 2 ** attempt
                                logger.warning(
                                    f"[LLMClient] Retryable error, retrying in {delay}s"
                                )
                                await asyncio.sleep(delay)
                                last_error = f"API error: {response.status_code}"
                                continue

                        yield f"API 错误: {response.status_code}"
                        return

                    # 收集工具调用（流式情况下需要累积）
                    accumulated_tool_calls: Dict[str, Dict] = {}

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue

                        data = line[5:].strip()

                        if data == "[DONE]":
                            break

                        try:
                            chunk_data = json.loads(data)

                            # 提取内容
                            content = self._extract_content(chunk_data)
                            if content:
                                yield content

                            # 提取工具调用
                            choice = chunk_data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            tool_calls_delta = delta.get("tool_calls", [])

                            for tc in tool_calls_delta:
                                call_id = tc.get("id", "")
                                function = tc.get("function", {})

                                if call_id:
                                    if call_id not in accumulated_tool_calls:
                                        accumulated_tool_calls[call_id] = {
                                            "id": call_id,
                                            "name": function.get("name", ""),
                                            "arguments": ""
                                        }

                                    # 累积参数字符串
                                    if "arguments" in function:
                                        accumulated_tool_calls[call_id]["arguments"] += function["arguments"]

                        except json.JSONDecodeError:
                            logger.debug(f"[LLMClient] Failed to parse chunk: {data}")
                            continue

                    # 发送完整的工具调用
                    for call_data in accumulated_tool_calls.values():
                        if call_data["name"]:  # 只有有名称的才是有效调用
                            try:
                                arguments = json.loads(call_data["arguments"])
                            except json.JSONDecodeError:
                                arguments = {}

                            yield ToolCall(
                                id=call_data["id"],
                                name=call_data["name"],
                                arguments=arguments
                            )

                    return

            except httpx.TimeoutException as e:
                logger.error(f"[LLMClient] Request timeout after {self.timeout}s")
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
                    last_error = str(e)
                    continue
                raise AgentError(f"LLM 请求超时")

            except Exception as e:
                logger.error(f"[LLMClient] Unexpected error: {e}")
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
                    last_error = str(e)
                    continue
                raise AgentError(f"LLM 调用失败: {e}")

        if last_error:
            logger.error(f"[LLMClient] All retries failed: {last_error}")
            raise AgentError(f"LLM 调用失败: {last_error}")

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> tuple[str, List[ToolCall]]:
        """支持工具调用的非流式聊天

        Args:
            messages: 消息列表
            tools: 工具定义列表
            system_prompt: 系统提示词（可选）

        Returns:
            tuple[str, List[ToolCall]]: (响应内容, 工具调用列表)
        """
        content_parts = []
        tool_calls = []

        async for chunk in self.stream_chat_with_tools(messages, tools, system_prompt):
            if isinstance(chunk, ToolCall):
                tool_calls.append(chunk)
            else:
                content_parts.append(chunk)

        return ("".join(content_parts), tool_calls)

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
