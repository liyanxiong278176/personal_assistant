"""LLM service using DashScope SDK (通义千问).

References:
- D-10: Use Tongyi Qianwen (DashScope API) as primary LLM
- D-11: Use DashScope SDK official Python package
- D-12: Model version: qwen-plus
- D-13: API key via environment variable
- D-17: Context window: last 20 messages or max 4000 tokens
- D-18: Single request max tokens: input 2000 + output 2000
- D-19: Implement question caching
- D-21: Timeout: single request max 30 seconds
- RESEARCH.md: DashScope streaming API pattern
"""

import asyncio
import logging
import os
from typing import AsyncGenerator, Optional

import dashscope
from dashscope import Generation

from app.cache import cache
from app.db.postgres import get_context_window
from app.models import ContextWindow

# Configuration from environment (per .env.example)
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen-plus")  # D-12
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", "2000"))  # D-18
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2000"))  # D-18
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))  # D-21
CONTEXT_MESSAGE_LIMIT = int(os.getenv("CONTEXT_MESSAGE_LIMIT", "20"))  # D-17
CONTEXT_TOKEN_LIMIT = int(os.getenv("CONTEXT_TOKEN_LIMIT", "4000"))  # D-17

if DASHSCOPE_API_KEY:
    dashscope.api_key = DASHSCOPE_API_KEY

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM interactions with streaming and cost controls."""

    def __init__(self):
        self._check_cache = True  # Enable caching per D-19

    async def _build_messages(
        self,
        user_message: str,
        conversation_id: Optional[str]
    ) -> list:
        """Build message list with context.

        Args:
            user_message: Current user message
            conversation_id: Conversation ID for context retrieval

        Returns:
            List of messages in DashScope format
        """
        messages = []

        # System prompt for travel assistant
        system_prompt = (
            "你是AI旅游助手，专门帮助用户规划旅行、推荐景点和提供旅游建议。"
            "请用友好的语气回答，提供实用的旅行信息。"
        )
        messages.append({"role": "system", "content": system_prompt})

        # Add conversation context if available (per D-17: CHAT-03)
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
        """Check cache for exact question match (per D-19).

        Args:
            user_message: User's question
            context_messages: Context messages for cache key

        Returns:
            Cached response if found, None otherwise
        """
        if not self._check_cache:
            return None

        # Build context for cache (exclude system prompt)
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
        """Stream chat response from LLM.

        Args:
            user_message: User's message
            conversation_id: Conversation ID for context
            on_stop: Event for user interruption (per D-20)

        Yields:
            Response content chunks

        Raises:
            Exception: If API call fails or timeout occurs
        """
        if not DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY not configured")

        # Build messages with context
        messages = await self._build_messages(user_message, conversation_id)

        # Check cache first (per D-19)
        cached = await self._check_question_cache(user_message, messages)
        if cached:
            # Yield cached response in chunks for streaming consistency
            chunk_size = 20
            for i in range(0, len(cached), chunk_size):
                if on_stop and on_stop.is_set():
                    logger.info("Response interrupted by user (cached)")
                    return
                yield cached[i:i + chunk_size]
                await asyncio.sleep(0.01)  # Simulate streaming
            return

        # Call DashScope API with streaming
        logger.info(f"Calling DashScope API: model={MODEL_NAME}, messages={len(messages)}")

        try:
            # Timeout wrapper (per D-21)
            response = await asyncio.wait_for(
                self._call_dashscope_streaming(messages, on_stop),
                timeout=REQUEST_TIMEOUT
            )

            # Accumulate response for caching
            full_response = ""

            async for chunk in response:
                if on_stop and on_stop.is_set():
                    logger.info("Response interrupted by user")
                    return

                if chunk:
                    full_response += chunk
                    yield chunk

            # Cache the response (per D-19)
            if full_response:
                cache_context = [m for m in messages if m.get("role") != "system"]
                cache.set(user_message, cache_context, full_response)

        except asyncio.TimeoutError:
            logger.error(f"LLM request timeout after {REQUEST_TIMEOUT}s")
            raise Exception(f"请求超时（{REQUEST_TIMEOUT}秒）")
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            raise

    async def _call_dashscope_streaming(
        self,
        messages: list,
        on_stop: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[str, None]:
        """Call DashScope API with streaming.

        This wraps the synchronous DashScope SDK in an async generator.

        Args:
            messages: Message list for LLM
            on_stop: Event for user interruption

        Yields:
            Response content chunks
        """
        # DashScope call with streaming
        responses = Generation.call(
            model=MODEL_NAME,
            messages=messages,
            stream=True,
            max_tokens=MAX_OUTPUT_TOKENS,  # D-18
            result_format="message"
        )

        # Process streaming response
        for response in responses:
            # Check for user interruption (per D-20)
            if on_stop and on_stop.is_set():
                break

            if response.status_code == 200:
                # Extract text content from streaming response
                if hasattr(response.output, "choices") and response.output.choices:
                    content = response.output.choices[0].message.content
                    if content:
                        yield content
                elif hasattr(response.output, "text"):
                    # Fallback for older API format
                    yield response.output.text
            else:
                error_msg = response.message if hasattr(response, "message") else "Unknown error"
                logger.error(f"DashScope API error: {error_msg}")
                raise Exception(f"API调用失败: {error_msg}")

            # Small delay to prevent overwhelming the client
            await asyncio.sleep(0.01)


# Global LLM service instance
llm_service = LLMService()
