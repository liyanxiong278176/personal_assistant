"""RuleStrategy - Improved keyword and pattern based intent classification.

Priority: 10 (high priority, but after cache and image check)
Cost: 0.0 (no LLM calls)

Design:
    - Only handles simple queries (short, no complex words)
    - Multi-dimensional scoring with capped confidence
    - Maximum 0.9 confidence (leaves room for LLM to reach 1.0)
    - Uses centralized keyword definitions from keywords.py
"""

import logging
import re
from typing import Dict, List, Optional

from app.core.context import RequestContext, IntentResult
from app.core.intent.keywords import (
    ALL_INTENT_KEYWORDS,
    ALL_INTENT_PATTERNS,
)

logger = logging.getLogger(__name__)


class RuleStrategy:
    """Improved keyword and pattern matching intent classification.

    Scoring algorithm:
        1. Keyword match: Add weighted score per keyword
        2. Pattern match: Add 0.15 per pattern match
        3. Apply cap: min(score, max_confidence)

    Max scores:
        - Keywords: 3 keywords × 0.3 = 0.9
        - Patterns: 2 patterns × 0.15 = 0.3
        - Combined: 0.9 (capped)

    This ensures:
        - Simple queries get fast classification
        - Complex queries flow to LLM
        - No "one keyword = 1.0" problem
    """

    def __init__(
        self,
        max_confidence: float = 0.9,
        keyword_weight: float = 1.0,
        pattern_weight: float = 0.15,
        max_length: int = 20,
        complex_words: Optional[List[str]] = None,
    ):
        """Initialize rule strategy.

        Args:
            max_confidence: Maximum confidence this strategy can return
            keyword_weight: Multiplier for keyword scores (for tuning)
            pattern_weight: Score per pattern match
            max_length: Max message length for this strategy
            complex_words: Words that trigger skip to LLM
        """
        self._max_confidence = max_confidence
        self._keyword_weight = keyword_weight
        self._pattern_weight = pattern_weight
        self._max_length = max_length
        self._complex_words = complex_words or ["规划", "定制", "推荐", "安排", "设计"]

    @property
    def priority(self) -> int:
        """Priority 10 - executes after cache/image checks."""
        return 10

    def estimated_cost(self) -> float:
        """Zero cost - no LLM calls involved."""
        return 0.0

    async def can_handle(self, context: RequestContext) -> bool:
        """Check if this strategy should handle the request.

        Returns False for:
            - Messages with images (handled by image strategy)
            - Messages marked as complex (should go to LLM)
            - Messages longer than max_length
            - Messages containing complex words

        Args:
            context: The request context

        Returns:
            True if this strategy should attempt classification
        """
        message = context.message

        # Skip if has image
        if context.has_image:
            logger.debug("[RuleStrategy] Skipping - has image")
            return False

        # Skip if externally marked complex
        if context.is_complex:
            logger.debug("[RuleStrategy] Skipping - marked complex")
            return False

        # Skip if too long
        if len(message) > self._max_length:
            logger.debug(f"[RuleStrategy] Skipping - message too long ({len(message)} > {self._max_length})")
            return False

        # Skip if contains complex words
        for word in self._complex_words:
            if word in message:
                logger.debug(f"[RuleStrategy] Skipping - contains complex word '{word}'")
                return False

        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using improved keyword and pattern scoring.

        Iterates through ALL_INTENT_KEYWORDS and ALL_INTENT_PATTERNS
        to support all intent types (itinerary, query, chat, hotel, food, budget, transport).

        Args:
            context: The request context

        Returns:
            IntentResult with intent, confidence (0.0-0.9), method="rule"
        """
        message = context.message

        # Score each intent type using centralized definitions
        scores: Dict[str, float] = {}
        for intent_name, keywords in ALL_INTENT_KEYWORDS.items():
            patterns = ALL_INTENT_PATTERNS.get(intent_name, [])
            scores[intent_name] = self._score_intent(message, keywords, patterns)

        # Find best intent
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # No meaningful matches
        if best_score < 0.1:
            logger.debug(f"[RuleStrategy] No matches found, returning low confidence chat")
            return IntentResult(
                intent="chat",
                confidence=0.1,
                method="rule",
                reasoning="No keyword or pattern matches found"
            )

        # Apply cap
        final_confidence = min(best_score, self._max_confidence)

        logger.debug(
            f"[RuleStrategy] Classified as {best_intent} with confidence {final_confidence:.2f} "
            f"(raw scores: {scores})"
        )

        return IntentResult(
            intent=best_intent,
            confidence=final_confidence,
            method="rule",
            reasoning=f"Matched {best_intent} with score {best_score:.2f}"
        )

    def _score_intent(
        self,
        message: str,
        keywords: Dict[str, float],
        patterns: List[str]
    ) -> float:
        """Calculate intent match score with keywords and patterns.

        Args:
            message: User message to score
            keywords: Dict of keyword -> weight mappings
            patterns: List of regex patterns

        Returns:
            Combined score from keyword and pattern matches
        """
        score = self._score_keywords_only(message, keywords)

        # Add pattern matches
        for pattern in patterns:
            if re.search(pattern, message):
                score += self._pattern_weight
                logger.debug(f"[RuleStrategy] Pattern matched: {pattern}")

        return score

    def _score_keywords_only(
        self,
        message: str,
        keywords: Dict[str, float]
    ) -> float:
        """Calculate score from keyword matches only.

        Args:
            message: User message to score
            keywords: Dict of keyword -> weight mappings

        Returns:
            Sum of weights for matched keywords
        """
        score = 0.0
        matched_keywords = []

        for keyword, weight in keywords.items():
            if keyword in message:
                score += weight * self._keyword_weight
                matched_keywords.append(keyword)

        if matched_keywords:
            logger.debug(f"[RuleStrategy] Matched keywords: {matched_keywords}")

        return score
