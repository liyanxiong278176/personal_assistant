"""SemanticValidator - LLM-based secondary validation for suspicious intent results.

This strategy validates RuleStrategy results when exclusion keywords are hit,
preventing false positives like "天气真好想去北京玩" being classified as query.

Priority: 15 (between RuleStrategy=10 and LLMStrategy=100)
Cost: ~150 tokens (short validation prompt)

Design:
    - Only triggered when RuleStrategy result has exclusion_keywords metadata
    - Uses lightweight LLM prompt for semantic validation
    - Can correct intent classification if keywords are in wrong context
"""

import json
import logging
import re
from typing import Optional

from app.core.context import RequestContext, IntentResult

logger = logging.getLogger(__name__)

# Lightweight validation prompt
_VALIDATION_PROMPT = """判断意图分类是否正确。

用户消息: "{message}"
初步判定意图: {intent}
命中关键词: {keywords}

注意：关键词可能出现在非意图相关语境：
- "天气真好想去旅游"中的"天气"并非查询意图，而是行程规划
- "聊聊酒店选择"中的"酒店"并非预订意图，而是闲聊

请判断初步判定是否正确，返回JSON：
{{"valid": true/false, "correct_intent": "正确意图", "reasoning": "简要说明"}}

只返回JSON，不要其他内容。"""


class SemanticValidator:
    """语义验证策略 - 对可疑结果进行 LLM 二次确认.

    Triggered when:
    - RuleStrategy confidence >= 0.7 and exclusion keywords were hit
    - Or result has metadata indicating potential semantic mismatch

    Uses lightweight LLM prompt to validate semantic correctness.
    """

    def __init__(
        self,
        llm_client=None,
        model: str = "deepseek-v4-flash",
        min_confidence: float = 0.7,  # Minimum confidence to trigger validation
        timeout: int = 15,  # Shorter timeout for validation
    ):
        """Initialize semantic validator.

        Args:
            llm_client: LLM client for validation calls
            model: Model name for validation
            min_confidence: Minimum confidence threshold to trigger validation
            timeout: Request timeout in seconds (shorter than full classification)
        """
        self._llm_client = llm_client
        self._model = model
        self._min_confidence = min_confidence
        self._timeout = timeout

    @property
    def priority(self) -> int:
        """Priority 15 - after RuleStrategy, before LLMStrategy."""
        return 15

    def estimated_cost(self) -> float:
        """Estimated token cost for validation."""
        return 150.0  # Approximately 150 tokens per validation

    def should_validate(self, result: IntentResult) -> bool:
        """Check if result should be validated.

        Args:
            result: IntentResult from previous strategy

        Returns:
            True if validation should be triggered
        """
        # Only validate RuleStrategy results with sufficient confidence
        if result.method != "rule":
            return False

        if result.confidence < self._min_confidence:
            return False

        # Check if exclusion keywords were hit
        if result.metadata and "exclusion_keywords" in result.metadata:
            return True

        return False

    async def validate(
        self,
        context: RequestContext,
        result: IntentResult
    ) -> IntentResult:
        """Validate intent classification using LLM.

        Args:
            context: Request context
            result: Initial classification result to validate

        Returns:
            Either corrected IntentResult or original result
        """
        if not self.should_validate(result):
            return result

        if not self._llm_client:
            logger.warning("[SemanticValidator] No LLM client, skipping validation")
            return result

        # Build validation prompt
        exclusion_keywords = result.metadata.get("exclusion_keywords", [])
        prompt = _VALIDATION_PROMPT.format(
            message=context.message,
            intent=result.intent,
            keywords=", ".join(exclusion_keywords)
        )

        try:
            # Call LLM for validation
            response = await self._call_llm(prompt)
            validation = self._parse_response(response)

            if validation and not validation.get("valid", True):
                # Intent was incorrect, use corrected intent
                correct_intent = validation.get("correct_intent", result.intent)
                reasoning = validation.get("reasoning", "Semantic correction")

                logger.info(
                    f"[SemanticValidator] Corrected intent: {result.intent} -> {correct_intent}"
                )

                return IntentResult(
                    intent=correct_intent,
                    confidence=0.65,  # Moderate confidence after correction
                    method="semantic_correction",
                    reasoning=reasoning,
                    strategy="SemanticValidator",
                )

            else:
                # Validation passed, return original result
                logger.debug(
                    f"[SemanticValidator] Validated {result.intent} as correct"
                )
                return result

        except Exception as e:
            logger.error(f"[SemanticValidator] Validation failed: {e}")
            # On error, return original result (fail-safe)
            return result

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with timeout.

        Args:
            prompt: Validation prompt

        Returns:
            LLM response string
        """
        response = await self._llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=None,
        )
        return response

    def _parse_response(self, response: str) -> Optional[dict]:
        """Parse LLM validation response.

        Args:
            response: Raw LLM response

        Returns:
            Parsed dict with valid, correct_intent, reasoning or None
        """
        if not response:
            return None

        # Try direct JSON parse
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
        json_match = re.search(r'\{[^{}]*"valid"[^{}]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning(f"[SemanticValidator] Could not parse response: {response[:200]}")
        return None