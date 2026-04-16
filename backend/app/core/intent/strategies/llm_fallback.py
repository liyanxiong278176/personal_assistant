"""LLMStrategy - LLM-based intent classification (no二次判断).

Priority: 100 (fallback - executes when rule strategy fails)
Cost: ~300 tokens

Design:
    - Trusts LLM's confidence output directly
    - No二次判断 - LLM's judgment is final
    - Can return confidence 0.0-1.0 (full range)
    - Supports 7 fine-grained intent types for travel assistant
"""

import json
import logging
import re
from typing import Optional

from app.core.context import RequestContext, IntentResult

logger = logging.getLogger(__name__)

# Classification prompt template - optimized for structured output
_CLASSIFICATION_PROMPT = """你是一个旅游助手意图分类专家。分析用户消息，判断用户意图。

用户消息：{message}

请判断用户意图并返回JSON：
{{
  "intent": "itinerary|query|hotel|food|budget|transport|chat|image",
  "confidence": 0.0-1.0,
  "reasoning": "简要说明判断依据"
}}

意图说明：
- itinerary: 用户想要规划/调整旅行行程（如"帮我规划北京三日游"、"制定旅游计划"）
- query: 用户想查询具体信息（如"北京天气怎么样"、"故宫开放时间"、"景点门票价格"）
- hotel: 用户查询/预订住宿（如"找酒店"、"住哪里"、"住宿推荐"、"民宿"）
- food: 用户查询美食/餐厅（如"推荐美食"、"有什么好吃的"、"当地特色菜"）
- budget: 用户询问预算/费用（如"预算多少"、"大概多少钱"、"花费"）
- transport: 用户询问交通方式（如"怎么去"、"交通方式"、"坐高铁"、"坐飞机"）
- chat: 普通对话、问候、闲聊（如"你好"、"谢谢"、"在吗"）
- image: 用户上传图片需要识别

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
            model: Model name for classification
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
        """
        self._llm_client = llm_client
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def priority(self) -> int:
        """Priority 100 - executes last as fallback."""
        return 100

    def estimated_cost(self) -> float:
        """Estimated token cost for LLM classification."""
        return 300.0  # Approximately 300 tokens per classification

    async def can_handle(self, context: RequestContext) -> bool:
        """Always returns True - this is the fallback strategy."""
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using LLM.

        Args:
            context: The request context

        Returns:
            IntentResult with intent, confidence, method="llm"
        """
        if not self._llm_client:
            # No LLM client available - return default
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
        """
        try:
            # Use chat method for simple completion
            response = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None,
            )
            return response
        except Exception as e:
            raise  # Re-raise for retry logic

    def _parse_response(self, response: str) -> Optional[dict]:
        """Parse LLM response to extract intent and confidence.

        Args:
            response: Raw LLM response string

        Returns:
            Parsed dict with intent, confidence, reasoning or None
        """
        if not response:
            return None

        # Try direct JSON parse first
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in response
        json_match = re.search(r'\{[^{}]*"intent"[^{}]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: extract intent and confidence using regex
        intent_match = re.search(r'"intent"\s*:\s*"([^"]+)"', response)
        conf_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', response)

        if intent_match and conf_match:
            return {
                "intent": intent_match.group(1),
                "confidence": float(conf_match.group(1)),
                "reasoning": "Parsed from partial response",
            }

        logger.warning(f"[LLMStrategy] Could not parse response: {response[:200]}")
        return None

    def _fallback_result(self, reason: str) -> IntentResult:
        """Return fallback result when LLM fails.

        Args:
            reason: Reason for fallback

        Returns:
            IntentResult with default chat intent
        """
        return IntentResult(
            intent="chat",
            confidence=0.5,
            method="llm",
            reasoning=f"LLM failed, using fallback: {reason}"
        )


# Legacy alias for backward compatibility
LLMFallbackStrategy = LLMStrategy
