"""Memory promotion mechanism for Agent Core.

This module provides intelligent memory promotion from short-term (episodic)
to long-term (semantic) memory based on importance scoring and content analysis.

The MemoryPromoter evaluates episodic memories and promotes important ones
to semantic memory, ensuring persistent storage of valuable user preferences
and information.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from app.core.memory.hierarchy import (
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
)

logger = logging.getLogger(__name__)


# Keywords that suggest preference content
PREFERENCE_KEYWORDS = {
    # Chinese preference indicators
    "喜欢", "爱", "偏好", "倾向", "习惯", "通常", "总是", "经常",
    "想要", "希望", "期待", "愿意", "更", "最", "特别", "尤其",
    # English preference indicators
    "like", "love", "prefer", "favorite", "usually", "always", "often",
    "want", "hope", "expect", "willing", "more", "most", "especially",
}

# Keywords that suggest important facts
FACT_KEYWORDS = {
    # Chinese fact indicators
    "预算", "钱", "费用", "时间", "日期", "地点", "目的地", "人数",
    "天", "晚", "住宿", "机票", "火车", "酒店", "景点", "活动",
    # English fact indicators
    "budget", "cost", "price", "time", "date", "place", "destination",
    "people", "days", "nights", "hotel", "flight", "train", "activity",
}

# Keywords that suggest constraints
CONSTRAINT_KEYWORDS = {
    # Chinese constraint indicators
    "不能", "不要", "避免", "限制", "只能", "必须", "需要", "要求",
    "不超过", "至少", "最多", "最少",
    # English constraint indicators
    "cannot", "avoid", "limit", "only", "must", "need", "require",
    "not exceed", "at least", "at most",
}


@dataclass
class PromotionResult:
    """Result of a memory promotion operation.

    Attributes:
        promoted_count: Number of memories promoted
        skipped_count: Number of memories skipped (not important enough)
        errors: List of error messages if any
        promoted_ids: List of promoted memory item IDs
    """

    promoted_count: int = 0
    skipped_count: int = 0
    errors: List[str] = None
    promoted_ids: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.promoted_ids is None:
            self.promoted_ids = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "promoted_count": self.promoted_count,
            "skipped_count": self.skipped_count,
            "errors": self.errors,
            "promoted_ids": self.promoted_ids,
        }


class MemoryPromoter:
    """Intelligent memory promotion from episodic to semantic memory.

    This class evaluates episodic memories based on multiple criteria:
    - Keyword matching (preference, fact, constraint indicators)
    - Content length (substantial content is more important)
    - Access frequency (frequently accessed content is important)
    - Confidence scores (higher confidence indicates importance)

    Example usage:
        ```python
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        # Add episodic memory
        hierarchy.add_episodic(MemoryItem(
            content="用户喜欢自然景观",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE
        ))

        # Promote important memories
        result = await promoter.promote_episodic_to_semantic("user123")
        print(f"Promoted {result.promoted_count} memories")
        ```
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        importance_threshold: float = 0.7,
    ):
        """Initialize the memory promoter.

        Args:
            hierarchy: MemoryHierarchy instance to promote memories from
            importance_threshold: Minimum importance score for promotion (0.0 to 1.0)
        """
        self._hierarchy = hierarchy
        self._importance_threshold = importance_threshold

        # Track access counts for memory items
        self._access_counts: Dict[str, int] = {}

        logger.info(
            f"[MemoryPromoter] Initialized with threshold={importance_threshold}"
        )

    async def promote_episodic_to_semantic(
        self,
        user_id: str,
        conversation_id: Optional[UUID] = None,
        llm_client: Optional[Any] = None,
    ) -> int:
        """Promote important episodic memories to semantic memory.

        Evaluates all episodic memories and promotes those that meet
        the importance threshold to semantic memory.

        Args:
            user_id: User ID for semantic memory storage
            conversation_id: Optional conversation ID for filtering
            llm_client: Optional LLM client for enhanced importance evaluation

        Returns:
            Number of memories promoted

        Examples:
            >>> count = await promoter.promote_episodic_to_semantic("user123")
            >>> print(f"Promoted {count} memories to semantic storage")
        """
        episodic_memories = self._hierarchy.get_episodic(limit=100)

        if not episodic_memories:
            logger.debug("[MemoryPromoter] No episodic memories to evaluate")
            return 0

        promoted_count = 0

        for memory in episodic_memories:
            # Skip already promoted memories
            if memory.level == MemoryLevel.SEMANTIC:
                continue

            # Calculate importance score
            importance = self._calculate_importance(memory)

            # Optionally use LLM for enhanced evaluation
            if llm_client is not None:
                llm_importance = await self._evaluate_with_llm(memory, llm_client)
                # Average the two scores
                importance = (importance + llm_importance) / 2

            # Update memory importance
            memory.importance = importance

            # Promote if threshold met
            if importance >= self._importance_threshold:
                # Create semantic memory copy
                semantic_item = MemoryItem(
                    content=memory.content,
                    level=MemoryLevel.SEMANTIC,
                    memory_type=memory.memory_type,
                    metadata=memory.metadata.copy(),
                    confidence=memory.confidence,
                    importance=importance,
                )

                self._hierarchy.add_semantic(semantic_item)
                promoted_count += 1

                logger.info(
                    f"[MemoryPromoter] Promoted episodic to semantic: "
                    f"'{memory.content[:50]}...' (importance={importance:.2f})"
                )

        logger.info(
            f"[MemoryPromoter] Promoted {promoted_count}/{len(episodic_memories)} "
            f"episodic memories to semantic"
        )

        return promoted_count

    async def auto_promote_from_conversation(
        self,
        conversation_id: UUID,
        messages: List[Dict[str, str]],
        user_id: str,
    ) -> Dict[str, Any]:
        """Automatically extract and promote memories from conversation messages.

        Analyzes conversation messages to extract important information
        and promote relevant items to semantic memory.

        Args:
            conversation_id: Conversation UUID
            messages: List of message dicts with 'role' and 'content' keys
            user_id: User ID for semantic memory storage

        Returns:
            Dictionary with promotion results:
                - extracted_count: Number of memories extracted
                - promoted_count: Number of memories promoted
                - memories: List of promoted memory contents

        Examples:
            >>> messages = [
            ...     {"role": "user", "content": "我喜欢自然景观"},
            ...     {"role": "assistant", "content": "好的，我会推荐自然景观"}
            ... ]
            >>> result = await promoter.auto_promote_from_conversation(
            ...     conv_id, messages, "user123"
            ... )
        """
        result = {
            "extracted_count": 0,
            "promoted_count": 0,
            "memories": [],
            "errors": [],
        }

        for message in messages:
            # Only process user messages
            if message.get("role") != "user":
                continue

            content = message.get("content", "")
            if not content:
                continue

            # Check if this is a preference statement
            if not self._is_preference(content) and not self._is_fact(content):
                continue

            # Determine memory type
            memory_type = self._determine_memory_type(content)

            # Calculate importance
            importance = self._calculate_importance_from_content(content)

            # Create episodic memory
            memory = MemoryItem(
                content=content,
                level=MemoryLevel.EPISODIC,
                memory_type=memory_type,
                importance=importance,
                metadata={"conversation_id": str(conversation_id)},
            )

            self._hierarchy.add_episodic(memory)
            result["extracted_count"] += 1

            # Promote if important enough
            if importance >= self._importance_threshold:
                semantic_item = MemoryItem(
                    content=content,
                    level=MemoryLevel.SEMANTIC,
                    memory_type=memory_type,
                    importance=importance,
                    metadata={"conversation_id": str(conversation_id)},
                )

                self._hierarchy.add_semantic(semantic_item)
                result["promoted_count"] += 1
                result["memories"].append(content)

                logger.info(
                    f"[MemoryPromoter] Auto-promoted from conversation: "
                    f"'{content[:50]}...'"
                )

        logger.info(
            f"[MemoryPromoter] Auto-promotion complete: "
            f"{result['promoted_count']}/{result['extracted_count']} promoted"
        )

        return result

    def _is_preference(self, content: str) -> bool:
        """Check if content indicates a user preference.

        Args:
            content: Text content to analyze

        Returns:
            True if content appears to express a preference

        Examples:
            >>> promoter._is_preference("我喜欢自然景观")
            True
            >>> promoter._is_preference("今天天气怎么样")
            False
        """
        content_lower = content.lower()

        # Check for preference keywords
        for keyword in PREFERENCE_KEYWORDS:
            if keyword in content_lower:
                return True

        return False

    def _is_fact(self, content: str) -> bool:
        """Check if content contains factual information.

        Args:
            content: Text content to analyze

        Returns:
            True if content appears to contain facts
        """
        content_lower = content.lower()

        # Check for fact keywords
        for keyword in FACT_KEYWORDS:
            if keyword in content_lower:
                return True

        # Check for numbers (budget, dates, etc.)
        import re
        if re.search(r'\d+', content):
            return True

        return False

    def _is_constraint(self, content: str) -> bool:
        """Check if content expresses a constraint.

        Args:
            content: Text content to analyze

        Returns:
            True if content appears to express a constraint
        """
        content_lower = content.lower()

        for keyword in CONSTRAINT_KEYWORDS:
            if keyword in content_lower:
                return True

        return False

    def _determine_memory_type(self, content: str) -> MemoryType:
        """Determine the memory type based on content analysis.

        Args:
            content: Text content to analyze

        Returns:
            Most appropriate MemoryType for the content
        """
        if self._is_preference(content):
            return MemoryType.PREFERENCE
        elif self._is_constraint(content):
            return MemoryType.CONSTRAINT
        elif self._is_fact(content):
            return MemoryType.FACT
        else:
            return MemoryType.FACT  # Default to fact

    def _calculate_importance(self, memory: MemoryItem) -> float:
        """Calculate importance score for a memory item.

        Args:
            memory: MemoryItem to evaluate

        Returns:
            Importance score (0.0 to 1.0)
        """
        score = 0.0

        # Base score from existing importance
        score += memory.importance * 0.4

        # Content-based scoring
        content_score = self._calculate_importance_from_content(memory.content)
        score += content_score * 0.4

        # Memory type bonus
        if memory.memory_type == MemoryType.PREFERENCE:
            score += 0.15
        elif memory.memory_type == MemoryType.CONSTRAINT:
            score += 0.2
        elif memory.memory_type == MemoryType.FACT:
            score += 0.1

        # Confidence bonus
        score += memory.confidence * 0.1

        # Access frequency bonus
        access_count = self._access_counts.get(memory.item_id, 0)
        score += min(access_count * 0.05, 0.15)  # Max 0.15 bonus

        return min(score, 1.0)

    def _calculate_importance_from_content(self, content: str) -> float:
        """Calculate importance score based on content analysis.

        Args:
            content: Text content to analyze

        Returns:
            Importance score (0.0 to 1.0)
        """
        score = 0.0
        content_lower = content.lower()

        # Length score (substantial content is more important)
        length = len(content)
        if length > 50:
            score += 0.25
        elif length > 20:
            score += 0.15
        elif length > 5:
            score += 0.05

        # Keyword matching
        preference_matches = sum(1 for kw in PREFERENCE_KEYWORDS if kw in content_lower)
        fact_matches = sum(1 for kw in FACT_KEYWORDS if kw in content_lower)
        constraint_matches = sum(1 for kw in CONSTRAINT_KEYWORDS if kw in content_lower)

        # Score based on keyword matches (more generous scoring)
        score += min(preference_matches * 0.25, 0.5)
        score += min(fact_matches * 0.15, 0.3)
        score += min(constraint_matches * 0.25, 0.4)

        # Number/detection bonus (facts with numbers are important)
        import re
        if re.search(r'\d+', content_lower):  # Any number
            score += 0.15

        return min(score, 1.0)

    async def _evaluate_with_llm(
        self,
        memory: MemoryItem,
        llm_client: Any,
    ) -> float:
        """Evaluate memory importance using LLM.

        Args:
            memory: MemoryItem to evaluate
            llm_client: LLM client with async chat interface

        Returns:
            Importance score (0.0 to 1.0) as evaluated by LLM
        """
        try:
            prompt = f"""Evaluate the importance of this user statement for long-term memory.

Statement: "{memory.content}"

Rate on a scale of 0.0 to 1.0 where:
- 0.0-0.3: Not important (greetings, small talk, transient info)
- 0.4-0.6: Somewhat important (context for current conversation)
- 0.7-1.0: Very important (user preferences, constraints, key facts)

Respond with only a number."""

            # This is a simplified interface - actual implementation depends on LLM client
            # For now, return a default score
            logger.debug("[MemoryPromoter] LLM evaluation not fully implemented")
            return 0.5

        except Exception as e:
            logger.error(f"[MemoryPromoter] LLM evaluation failed: {e}")
            return 0.5

    def track_access(self, memory_id: str) -> None:
        """Track access to a memory item for importance calculation.

        Args:
            memory_id: ID of the memory being accessed
        """
        self._access_counts[memory_id] = self._access_counts.get(memory_id, 0) + 1
        logger.debug(f"[MemoryPromoter] Tracked access to memory {memory_id}")

    def get_access_count(self, memory_id: str) -> int:
        """Get access count for a memory item.

        Args:
            memory_id: ID of the memory

        Returns:
            Number of times the memory has been accessed
        """
        return self._access_counts.get(memory_id, 0)

    def reset_access_counts(self) -> None:
        """Reset all access counts."""
        self._access_counts.clear()
        logger.debug("[MemoryPromoter] Reset access counts")
