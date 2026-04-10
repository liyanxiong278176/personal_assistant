"""LLMStrategy - LLM-based intent classification (no二次判断).

Priority: 100 (fallback - executes when rule strategy fails)
Cost: ~300 tokens

Design:
    - Trusts LLM's confidence output directly
    - No二次判断 - LLM's judgment is final
    - Can return confidence 0.0-1.0 (full range)
"""

import json
import logging
import re
from typing import Optional

from app.core.context import RequestContext, IntentResult

logger = logging.getLogger(__name__)

# Classification prompt template - optimized for structured output
_CLASSIFICATION_PROMPT = """你是一个意图分类专家。分析用户消息，判断用户意图。

用户消息：{message}

请判断用户意图并返回JSON：
{{
  "intent": "itinerary|query|image|chat",
  "confidence": 0.0-1.0,
  "reasoning": "简要说明判断依据"
}}

意图说明：
- itinerary: 用户想要规划/调整旅行行程
- query: 用户想查询具体信息（天气、交通、景点等）
- image: 用户上传图片需要识别
- chat: 普通对话、问候、闲聊

置信度说明：
- 0.9-1.0: 意图非常明确，无需澄清
- 0.5-0.8: 意图较明确，可能需要澄清
- 0.0-0.5: 意图不明确，建议澄清或使用默认值

只返回JSON，不要其他内容。"""


class LLMStrategy:
    """LLM-based intent classification strategy.

    This is the fallback strategy (priority=100) that uses LLM
    to classify intent when rule-based strategies fail.

    Key design: Trusts LLM output directly - no二次判断.
    The LLM returns confidence based on full semantic understanding.
    """

    def __init__(
        self,
        llm_client=None,
        model: str = "deepseek-chat",
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """Initialize LLM strategy.

        Args:
            llm_client: LLM client for classification
            model: Model name to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self._llm_client = llm_client
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def priority(self) -> int:
        """Priority 100 - lowest, executes as fallback."""
        return 100

    def estimated_cost(self) -> float:
        """Estimated token cost for LLM classification."""
        return 300.0

    async def can_handle(self, context: RequestContext) -> bool:
        """Always returns True - fallback strategy handles any request.

        Args:
            context: The request context

        Returns:
            True - always available as fallback
        """
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using LLM.

        Returns LLM's confidence as-is - no二次判断.

        Args:
            context: The request context

        Returns:
            IntentResult with LLM's confidence directly
        """
        # Check if LLM client is available
        if self._llm_client is None:
            logger.warning("[LLMStrategy] No LLM client available")
            return IntentResult(
                intent="chat",
                confidence=0.5,
                method="llm",
                reasoning="No LLM client available, using default chat"
            )

        message = context.message

        # Build classification prompt
        prompt = _CLASSIFICATION_PROMPT.format(message=message)

        # Try with retries
        for attempt in range(self._max_retries):
            try:
                response = await self._call_llm(prompt)

                # Parse response
                result = self._parse_response(response)

                if result:
                    intent = result["intent"]
                    confidence = result["confidence"]
                    reasoning = result.get("reasoning", f"LLM classified as {intent}")

                    logger.info(
                        f"[LLMStrategy] Classified as {intent} with confidence {confidence:.2f}"
                    )

                    return IntentResult(
                        intent=intent,
                        confidence=confidence,  # Use LLM's confidence as-is
                        method="llm",
                        reasoning=reasoning
                    )
                else:
                    logger.warning(
                        f"[LLMStrategy] Failed to parse LLM response (attempt {attempt + 1})"
                    )
                    if attempt == self._max_retries - 1:
                        return self._fallback_result("Failed to parse LLM response")

            except Exception as e:
                logger.error(
                    f"[LLMStrategy] LLM call failed (attempt {attempt + 1}): {e}"
                )
                if attempt == self._max_retries - 1:
                    return self._fallback_result(f"LLM call failed: {e}")

        # Should not reach here, but just in case
        return self._fallback_result("Max retries exceeded")

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with timeout.

        Args:
            prompt: The classification prompt

        Returns:
            LLM response string

        Raises:
            TimeoutError: If LLM call times out
            Exception: For other LLM errors
        """
        # This is a placeholder - actual implementation depends on LLM client
        # For now, assume the client has a chat method
        import asyncio

        try:
            # Wrap with timeout
            response = await asyncio.wait_for(
                self._llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt="You are an intent classifier. Respond only with valid JSON."
                ),
                timeout=self._timeout
            )
            return response
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM call timed out after {self._timeout}s")

    def _parse_response(self, response: str) -> Optional[dict]:
        """Parse LLM response to extract intent, confidence, reasoning.

        Args:
            response: Raw LLM response string

        Returns:
            dict with 'intent', 'confidence', and optional 'reasoning'
        """
        response = response.strip()

        # Try direct JSON parse
        try:
            data = json.loads(response)
            if "intent" in data:
                return {
                    "intent": data["intent"],
                    "confidence": float(data.get("confidence", 0.5)),
                    "reasoning": data.get("reasoning", "")
                }
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        if "```" in response:
            parts = response.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:  # Content inside code blocks
                    lines = part.split("\n", 1)
                    json_content = lines[1] if len(lines) > 1 else part
                    try:
                        data = json.loads(json_content.strip())
                        if "intent" in data:
                            return {
                                "intent": data["intent"],
                                "confidence": float(data.get("confidence", 0.5)),
                                "reasoning": data.get("reasoning", "")
                            }
                    except json.JSONDecodeError:
                        continue

        # Try regex to find JSON object
        json_pattern = r'\{[^{}]*"intent"\s*:\s*"[^"]*"[^{}]*"confidence"\s*:\s*[0-9.]+[^{}]*\}'
        matches = re.findall(json_pattern, response)
        for match in matches:
            try:
                data = json.loads(match)
                return {
                    "intent": data["intent"],
                    "confidence": float(data.get("confidence", 0.5)),
                    "reasoning": data.get("reasoning", "")
                }
            except json.JSONDecodeError:
                continue

        return None

    def _fallback_result(self, reason: str) -> IntentResult:
        """Create a fallback result when LLM fails.

        Args:
            reason: Why LLM failed

        Returns:
            IntentResult with chat intent and low confidence
        """
        return IntentResult(
            intent="chat",
            confidence=0.5,
            method="llm",
            reasoning=f"LLM failed, using fallback: {reason}"
        )


# Legacy alias for backward compatibility
LLMFallbackStrategy = LLMStrategy
