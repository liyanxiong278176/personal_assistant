"""RuleStrategy - Keyword and pattern based intent classification.

Priority: 1 (highest, executes first)
Cost: 0.0 (no LLM calls)
"""

import re
from typing import Optional

from app.core.context import RequestContext
from app.core.intent.classifier import IntentResult

# Intent keyword definitions
ITINERARY_KEYWORDS = ["规划", "行程", "旅游", "旅行", "几天", "日游", "去玩", "计划", "安排", "路线", "设计"]
QUERY_KEYWORDS = ["天气", "温度", "怎么去", "门票", "价格", "开放时间", "地址", "景点"]
CHAT_KEYWORDS = ["你好", "在吗", "谢谢", "您好"]

# Intent patterns (regex)
ITINERARY_PATTERNS = [
    r"规划.*行程",
    r"制定.*计划",
    r"设计.*路线",
    r"去.{2,6}?玩",
    r"去.{2,6}?旅游",
    r".{2,6}?几天游",
]


class RuleStrategy:
    """Keyword and pattern matching intent classification strategy.

    This is the fastest strategy (priority=1, cost=0.0) that handles
    simple, unambiguous requests through keyword and regex pattern matching.
    """

    @property
    def priority(self) -> int:
        """Priority 1 - highest, executes first among all strategies."""
        return 1

    def estimated_cost(self) -> float:
        """Zero cost - no LLM calls involved."""
        return 0.0

    async def can_handle(self, context: RequestContext) -> bool:
        """Always returns True - rule strategy can attempt any request.

        Since this strategy has zero cost, it always attempts classification.
        """
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using keyword and pattern matching.

        Scoring:
        - Each keyword match adds 1.0 to score
        - Each pattern match adds 0.5 to score
        - Score is normalized to [0.0, 1.0] range

        Returns IntentResult with:
        - intent: "itinerary", "query", or "chat"
        - confidence: 0.0-1.0 based on match strength
        - method: "keyword"
        """
        message = context.message

        # Score each intent type
        scores = {}

        # Itinerary: keyword + pattern matching
        itinerary_score = self._score_intent(message, ITINERARY_KEYWORDS, ITINERARY_PATTERNS)
        if itinerary_score > 0:
            scores["itinerary"] = itinerary_score

        # Query: keyword matching only
        query_score = self._score_intent(message, QUERY_KEYWORDS, [])
        if query_score > 0:
            scores["query"] = query_score

        # Chat: keyword matching only
        chat_score = self._score_intent(message, CHAT_KEYWORDS, [])
        if chat_score > 0:
            scores["chat"] = chat_score

        # Determine best intent
        if not scores:
            # No matches - ambiguous/low confidence
            return IntentResult(
                intent="chat",
                confidence=0.3,
                method="keyword",
                reasoning="No keyword matches found"
            )

        # Find highest scoring intent
        best_intent = max(scores, key=scores.get)
        best_score = min(scores[best_intent], 1.0)  # Cap at 1.0

        return IntentResult(
            intent=best_intent,
            confidence=best_score,
            method="keyword",
            reasoning=f"Matched {best_intent} with score {best_score:.2f}"
        )

    def _score_intent(
        self,
        message: str,
        keywords: list[str],
        patterns: list[str]
    ) -> float:
        """Calculate intent match score.

        Args:
            message: User message to score
            keywords: List of keyword strings to match
            patterns: List of regex patterns to match

        Returns:
            Score based on keyword and pattern matches (not normalized)
        """
        score = 0.0

        # Keyword matches
        for keyword in keywords:
            if keyword in message:
                score += 1.0

        # Pattern matches
        for pattern in patterns:
            if re.search(pattern, message):
                score += 0.5

        return score
