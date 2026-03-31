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
        conversation_id: Optional[str],
        user_id: Optional[str] = None,
        custom_system_prompt: Optional[str] = None
    ) -> list:
        """Build message list with context and user preferences."""
        messages = []

        # Use custom system prompt if provided, otherwise build default
        if custom_system_prompt:
            system_prompt = custom_system_prompt
        else:
            # Build system prompt with user preferences
            system_prompt = await self._build_system_prompt(user_id)

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

    async def _build_system_prompt(self, user_id: Optional[str]) -> str:
        """Build system prompt with user preferences."""
        base_prompt = (
            "你是AI旅游助手，专门帮助用户规划旅行、推荐景点和提供旅游建议。"
            "请用友好的语气回答，提供实用的旅行信息。"
        )

        # Add user preferences if user_id provided
        if user_id:
            try:
                from app.db.postgres import get_preferences
                prefs = await get_preferences(user_id)
                if prefs:
                    # Build preference section
                    pref_parts = []
                    if prefs.get('budget'):
                        budget_map = {'low': '经济型', 'medium': '舒适型', 'high': '豪华型'}
                        budget_label = budget_map.get(prefs['budget'], prefs['budget'])
                        pref_parts.append(f"预算: {budget_label}")
                    if prefs.get('interests'):
                        interest_map = {
                            'history': '历史文化', 'food': '美食体验',
                            'nature': '自然风光', 'shopping': '购物',
                            'art': '艺术展览', 'entertainment': '娱乐休闲',
                            'sports': '户外运动', 'photography': '摄影打卡'
                        }
                        interests = [interest_map.get(i, i) for i in prefs['interests']]
                        pref_parts.append(f"兴趣: {', '.join(interests)}")
                    if prefs.get('style'):
                        style_map = {'relaxed': '悠闲放松', 'compact': '紧凑充实', 'adventure': '探索冒险'}
                        style_label = style_map.get(prefs['style'], prefs['style'])
                        pref_parts.append(f"风格: {style_label}")
                    if prefs.get('travelers', 1) > 1:
                        pref_parts.append(f"人数: {prefs['travelers']}人")

                    if pref_parts:
                        base_prompt += "\n\n## 用户偏好 (请在推荐时优先考虑)\n"
                        base_prompt += "\n".join(f"- {p}" for p in pref_parts)
                        base_prompt += "\n\n请根据这些偏好给出个性化推荐。"
            except Exception as e:
                logger.warning(f"Failed to load user preferences: {e}")

        return base_prompt

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
        on_stop: Optional[asyncio.Event] = None,
        user_id: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from LLM with true async interrupt support.

        Args:
            user_message: User's message
            conversation_id: Conversation ID for context
            on_stop: Event for user interruption
            user_id: User ID for personalization
            system_prompt: Optional custom system prompt (overrides default)

        Yields:
            Response content chunks

        Raises:
            Exception: If API call fails or timeout occurs
        """
        if not DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY not configured")

        # Build messages with context and user preferences
        messages = await self._build_messages(user_message, conversation_id, user_id, system_prompt)

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
