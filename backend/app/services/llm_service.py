"""LLM service using DashScope HTTP API (通义千问).

Uses HTTPX async client for true async streaming with interrupt support.

References:
- D-10: Use Tongyi Qianwen (DashScope API) as primary LLM
- D-12: Model version: qwen-plus
- D-13: API key via environment variable
- D-17: Context window: last 20 messages or max 4000 tokens
- D-18: Single request max tokens: input 2000 + output 2000
- D-19: Implement question caching
- D-20: Support user interruption
- D-21: Timeout: single request max 30 seconds
"""

import asyncio
import json
import logging
import os
from typing import AsyncGenerator, Optional

import httpx

from app.cache import cache
from app.db.postgres import get_context_window

# Configuration from environment
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen-plus")
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2000"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
CONTEXT_MESSAGE_LIMIT = int(os.getenv("CONTEXT_MESSAGE_LIMIT", "20"))
CONTEXT_TOKEN_LIMIT = int(os.getenv("CONTEXT_TOKEN_LIMIT", "4000"))

# DashScope API endpoint
DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM interactions with async streaming and interrupt support."""

    def __init__(self):
        self._check_cache = True
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTPX async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT + 10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _build_messages(
        self,
        user_message: str,
        conversation_id: Optional[str]
    ) -> list:
        """Build message list with context."""
        messages = []

        # System prompt
        system_prompt = (
            "你是AI旅游助手，专门帮助用户规划旅行、推荐景点和提供旅游建议。"
            "请用友好的语气回答，提供实用的旅行信息。"
        )
        messages.append({"role": "system", "content": system_prompt})

        # Add conversation context if available
        if conversation_id:
            try:
                context = await get_context_window(
                    conversation_id,
                    max_messages=CONTEXT_MESSAGE_LIMIT,
                    max_tokens=CONTEXT_TOKEN_LIMIT
                )
                messages.extend(context)
            except Exception as e:
                logger.warning(f"Failed to load context: {e}")

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _check_question_cache(
        self,
        user_message: str,
        context_messages: list
    ) -> Optional[str]:
        """Check cache for exact question match."""
        if not self._check_cache:
            return None

        cache_context = [m for m in context_messages if m.get("role") != "system"]
        cached_response = cache.get(user_message, cache_context)

        if cached_response:
            logger.info(f"Cache hit for question: {user_message[:50]}...")
            return cached_response

        return None

    async def stream_chat(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        on_stop: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from LLM with true async interrupt support.

        Args:
            user_message: User's message
            conversation_id: Conversation ID for context
            on_stop: Event for user interruption

        Yields:
            Response content chunks

        Raises:
            Exception: If API call fails or timeout occurs
        """
        if not DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY not configured")

        # Build messages with context
        messages = await self._build_messages(user_message, conversation_id)

        # Check cache first
        cached = await self._check_question_cache(user_message, messages)
        if cached:
            for i in range(0, len(cached), 20):
                if on_stop and on_stop.is_set():
                    logger.info("Response interrupted by user (cached)")
                    return
                yield cached[i:i + 20]
                await asyncio.sleep(0.01)
            return

        # Call DashScope API with async streaming
        logger.info(f"Calling DashScope API: model={MODEL_NAME}, messages={len(messages)}")

        try:
            client = await self._get_client()
            full_response = ""

            headers = {
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": MODEL_NAME,
                "messages": messages,
                "stream": True,
                "max_tokens": MAX_OUTPUT_TOKENS
            }

            async with client.stream(
                "POST",
                DASHSCOPE_API_URL,
                headers=headers,
                json=payload
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"DashScope API error: {response.status_code} - {error_text}")
                    raise Exception(f"API调用失败: {response.status_code}")

                # Process SSE stream
                async for line in response.aiter_lines():
                    # Check for stop signal frequently
                    if on_stop and on_stop.is_set():
                        logger.info("User requested stop, terminating stream")
                        return

                    if not line or not line.startswith("data:"):
                        continue

                    data = line[5:].strip()  # Remove "data:" prefix

                    if data == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data)
                        content = self._extract_content(chunk_data)
                        if content:
                            full_response += content
                            yield content
                    except json.JSONDecodeError:
                        logger.debug(f"Failed to parse chunk: {data}")
                        continue

            # Cache the response
            if full_response:
                cache_context = [m for m in messages if m.get("role") != "system"]
                cache.set(user_message, cache_context, full_response)

        except httpx.TimeoutException:
            logger.error(f"LLM request timeout after {REQUEST_TIMEOUT}s")
            raise Exception(f"请求超时（{REQUEST_TIMEOUT}秒）")
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            raise

    def _extract_content(self, chunk_data: dict) -> str:
        """Extract content from DashScope streaming chunk."""
        try:
            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
            return delta.get("content", "")
        except (KeyError, IndexError, TypeError):
            return ""


# Global LLM service instance
llm_service = LLMService()
