"""RuleStrategy - Improved keyword and pattern based intent classification.

Priority: 10 (high priority, but after cache and image check)
Cost: 0.0 (no LLM calls)

Design:
    - Only handles simple queries (short, no complex words)
    - Multi-dimensional scoring with capped confidence
    - Maximum 0.9 confidence (leaves room for LLM to reach 1.0)
    - Uses centralized keyword definitions from keywords.py
    - Supports negative keywords (exclusion rules) for Bad Case handling
"""

import logging
import re
from typing import Dict, List, Optional

from app.core.context import RequestContext, IntentResult
from app.core.intent.keywords import (
    ALL_INTENT_KEYWORDS,
    ALL_INTENT_PATTERNS,
    get_exclusion_keywords,
    has_exclusion_match,
)

logger = logging.getLogger(__name__)


class RuleStrategy:
    """Improved keyword and pattern matching intent classification.

    Optimized scoring algorithm:
        1. Keyword match: Add weighted score per keyword
        2. Pattern match: Add 0.25 per pattern match (increased from 0.15)
        3. Multi-match bonus: +0.1 for 2+ keywords, +0.15 for 3+ keywords
        4. Apply cap: min(score, max_confidence)

    Max scores (with optimizations):
        - Keywords: 3+ keywords × 0.5 + bonus ≈ 1.0+
        - Patterns: 2 patterns × 0.25 = 0.5
        - Combined: Can exceed 0.9 for confident matches

    This ensures:
        - Simple queries with clear intent get high confidence
        - Complex queries still flow to LLM
    """

    def __init__(
        self,
        max_confidence: float = 0.9,
        keyword_weight: float = 1.0,
        pattern_weight: float = 0.25,  # Increased from 0.15
        max_length: int = 50,
        complex_words: Optional[List[str]] = None,
        multi_match_bonus: bool = True,  # Enable multi-match bonus
    ):
        """Initialize rule strategy.

        Args:
            max_confidence: Maximum confidence this strategy can return
            keyword_weight: Multiplier for keyword scores
            pattern_weight: Score per pattern match (increased)
            max_length: Max message length for this strategy
            complex_words: Words that trigger skip to LLM
            multi_match_bonus: Enable bonus for multiple keyword matches
        """
        self._max_confidence = max_confidence
        self._keyword_weight = keyword_weight
        self._pattern_weight = pattern_weight
        self._max_length = max_length
        self._multi_match_bonus = multi_match_bonus
        self._complex_words = complex_words or ["定制", "设计"]

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
        exclusion_hits: Dict[str, List[str]] = {}  # Track exclusion matches

        for intent_name in ALL_INTENT_KEYWORDS.keys():
            keywords = ALL_INTENT_KEYWORDS.get(intent_name, {})
            patterns = ALL_INTENT_PATTERNS.get(intent_name, [])
            score, exclusions = self._score_intent_with_exclusions(
                message, intent_name, keywords, patterns
            )
            scores[intent_name] = score
            if exclusions:
                exclusion_hits[intent_name] = exclusions

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

        # Check if best intent hit exclusion (may need semantic validation)
        hit_exclusion = best_intent in exclusion_hits

        logger.debug(
            f"[RuleStrategy] Classified as {best_intent} with confidence {final_confidence:.2f} "
            f"(raw scores: {scores}, exclusion_hits: {exclusion_hits})"
        )

        result = IntentResult(
            intent=best_intent,
            confidence=final_confidence,
            method="rule",
            reasoning=f"Matched {best_intent} with score {best_score:.2f}"
        )

        # Mark if exclusion was hit (for semantic validation)
        if hit_exclusion:
            result.metadata = {"exclusion_keywords": exclusion_hits[best_intent]}

        return result

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

    def _score_intent_with_exclusions(
        self,
        message: str,
        intent_name: str,
        keywords: Dict[str, float],
        patterns: List[str]
    ) -> tuple[float, List[str]]:
        """Calculate intent score with exclusion (negative keyword) handling.

        Args:
            message: User message to score
            intent_name: Intent identifier for exclusion lookup
            keywords: Dict of keyword -> weight mappings
            patterns: List of regex patterns

        Returns:
            Tuple of (score, matched_exclusion_keywords)
        """
        # Base score from keywords and patterns
        score = self._score_keywords_only(message, keywords)

        # Add pattern matches
        for pattern in patterns:
            if re.search(pattern, message):
                score += self._pattern_weight
                logger.debug(f"[RuleStrategy] Pattern matched: {pattern}")

        # Apply negative keywords (exclusion rules)
        exclusions = get_exclusion_keywords(intent_name)
        matched_exclusions = []

        for keyword, penalty in exclusions.items():
            if keyword in message:
                score += penalty  # penalty is negative
                matched_exclusions.append(keyword)
                logger.debug(
                    f"[RuleStrategy] Exclusion matched for {intent_name}: "
                    f"'{keyword}' -> penalty {penalty}"
                )

        # Ensure score is non-negative
        final_score = max(score, 0.0)

        return final_score, matched_exclusions

    def _score_keywords_only(
        self,
        message: str,
        keywords: Dict[str, float]
    ) -> float:
        """Calculate score from keyword matches only with multi-match bonus.

        Args:
            message: User message to score
            keywords: Dict of keyword -> weight mappings

        Returns:
            Sum of weights for matched keywords + bonus
        """
        score = 0.0
        matched_keywords = []

        for keyword, weight in keywords.items():
            if keyword in message:
                score += weight * self._keyword_weight
                matched_keywords.append(keyword)

        if matched_keywords:
            logger.debug(f"[RuleStrategy] Matched keywords: {matched_keywords}")

            # Add multi-match bonus for confidence
            if self._multi_match_bonus:
                match_count = len(matched_keywords)
                if match_count >= 3:
                    score += 0.15  # Strong bonus for 3+ matches
                elif match_count >= 2:
                    score += 0.10  # Moderate bonus for 2+ matches

        return score
