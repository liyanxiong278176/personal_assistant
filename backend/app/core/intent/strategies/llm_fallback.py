"""LLMFallbackStrategy - LLM-based intent classification (fallback)

Priority: 100 (last resort)
Cost: ~300 tokens (configurable)
"""

import json
import logging
from typing import Optional

from app.core.context import RequestContext
from app.core.intent.classifier import IntentResult

logger = logging.getLogger(__name__)

# Classification prompt template
_CLASSIFICATION_PROMPT = """Classify the following user message into one of these intents:
- itinerary: User wants to plan a trip or itinerary
- query: User is asking for information (weather, traffic, tickets, etc.)
- chat: Casual conversation
- image: User is asking about image recognition

Respond in JSON format: {{"intent": "itinerary|query|chat|image", "confidence": 0.0-1.0}}

User message: {message}"""


class LLMFallbackStrategy:
    """LLM-based intent classification strategy (fallback).

    This is the last resort strategy (priority=100) that uses LLM
    to classify intent when all other strategies fail.

    Behavior:
    - If no LLM client: return intent="chat", confidence=0.5
    - If LLM fails: return intent="chat", confidence=0.5 with error reasoning
    - Otherwise: parse JSON response and return result
    """

    def __init__(self, llm_client=None, token_cost: float = 300.0):
        """Initialize LLM fallback strategy.

        Args:
            llm_client: Optional LLM client for classification
            token_cost: Estimated token cost for LLM calls (default 300)
        """
        self._llm_client = llm_client
        self._token_cost = token_cost

    @property
    def priority(self) -> int:
        """Priority 100 - lowest, executes as last resort."""
        return 100

    def estimated_cost(self) -> float:
        """Estimated token cost for LLM classification."""
        return self._token_cost

    async def can_handle(self, context: RequestContext) -> bool:
        """Always returns True - fallback strategy handles any request.

        Since this is the last resort strategy, it always attempts classification.
        """
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using LLM.

        Args:
            context: The request context containing message and metadata

        Returns:
            IntentResult: Classification result with intent, confidence,
                method, and optional reasoning
        """
        # Check if LLM client is available
        if self._llm_client is None:
            logger.warning("[LLMFallbackStrategy] No LLM client available")
            return IntentResult(
                intent="chat",
                confidence=0.5,
                method="llm",
                reasoning="No LLM client available, defaulting to chat"
            )

        message = context.message

        # Build classification prompt
        prompt = _CLASSIFICATION_PROMPT.format(message=message)

        try:
            # Call LLM for classification
            response = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are an intent classifier. Respond only with valid JSON."
            )

            # Parse JSON response
            result = self._parse_response(response)

            if result:
                logger.debug(
                    f"[LLMFallbackStrategy] Classified as {result['intent']} "
                    f"with confidence {result['confidence']}"
                )
                return IntentResult(
                    intent=result["intent"],
                    confidence=result["confidence"],
                    method="llm",
                    reasoning=f"LLM classified as {result['intent']}"
                )
            else:
                # Failed to parse, return default
                logger.warning(
                    f"[LLMFallbackStrategy] Failed to parse LLM response: {response[:100]}"
                )
                return IntentResult(
                    intent="chat",
                    confidence=0.5,
                    method="llm",
                    reasoning=f"Failed to parse LLM response, defaulting to chat"
                )

        except Exception as e:
            logger.error(f"[LLMFallbackStrategy] LLM call failed: {e}")
            return IntentResult(
                intent="chat",
                confidence=0.5,
                method="llm",
                reasoning=f"LLM call failed: {e}, defaulting to chat"
            )

    def _parse_response(self, response: str) -> Optional[dict]:
        """Parse LLM response to extract intent and confidence.

        Args:
            response: Raw LLM response string

        Returns:
            dict with 'intent' and 'confidence', or None if parsing fails
        """
        # Try to extract JSON from response
        response = response.strip()

        # Try direct JSON parse
        try:
            data = json.loads(response)
            if "intent" in data:
                return {
                    "intent": data["intent"],
                    "confidence": float(data.get("confidence", 0.5))
                }
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        if "```" in response:
            # Extract content between code blocks
            parts = response.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:  # Content inside code blocks
                    # Remove language identifier (e.g., "json")
                    lines = part.split("\n", 1)
                    json_content = lines[1] if len(lines) > 1 else part
                    try:
                        data = json.loads(json_content.strip())
                        if "intent" in data:
                            return {
                                "intent": data["intent"],
                                "confidence": float(data.get("confidence", 0.5))
                            }
                    except json.JSONDecodeError:
                        continue

        # Try regex to find JSON object
        import re
        json_pattern = r'\{[^{}]*"intent"\s*:\s*"[^"]*"[^{}]*"confidence"\s*:\s*[0-9.]+[^{}]*\}'
        matches = re.findall(json_pattern, response)
        for match in matches:
            try:
                data = json.loads(match)
                return {
                    "intent": data["intent"],
                    "confidence": float(data.get("confidence", 0.5))
                }
            except json.JSONDecodeError:
                continue

        return None
