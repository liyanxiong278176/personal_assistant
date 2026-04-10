"""IntentRouter configuration - Simplified with unified confidence thresholds.

Design principles:
    - Unified confidence semantics across all strategies
    - Single high threshold (0.8) for immediate acceptance
    - Single mid threshold (0.5) for clarification
    - No二次判断 - trust each strategy's output
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class KeywordConfig(BaseModel):
    """Configuration for keyword-based classification.

    Only applies to simple queries (short length, no complex words).
    """
    max_length: int = Field(
        default=20,
        ge=10,
        le=50,
        description="Maximum message length for keyword-only classification"
    )
    complex_words: List[str] = Field(
        default_factory=lambda: ["规划", "定制", "推荐", "安排", "设计"],
        description="Words that trigger LLM classification"
    )
    accept_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum score to accept keyword classification"
    )
    keyword_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight per keyword match (max 3 keywords = 0.9)"
    )
    pattern_weight: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Weight per pattern match (max 2 patterns = 0.3)"
    )
    max_confidence: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Maximum confidence for keyword classification (leaves room for LLM)"
    )


class CacheConfig(BaseModel):
    """Configuration for classification result cache."""
    enabled: bool = Field(
        default=True,
        description="Whether to enable result caching"
    )
    max_size: int = Field(
        default=1000,
        ge=0,
        description="Maximum number of cached results"
    )


class LLMConfig(BaseModel):
    """Configuration for LLM fallback strategy."""
    timeout: int = Field(
        default=30,
        ge=5,
        le=120,
        description="LLM request timeout in seconds"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retries on failure"
    )
    model: str = Field(
        default="deepseek-chat",
        description="Default LLM model for classification"
    )


class IntentRouterConfig(BaseModel):
    """Unified configuration for intent classification.

    Confidence thresholds (applied uniformly to all strategies):
        - high_confidence: >= 0.8 → accept immediately
        - mid_confidence: 0.5 - 0.8 → can trigger clarification
        - low_confidence: < 0.5 → try next strategy

    No二次判断 - each strategy's confidence is trusted.
    """

    # Unified confidence thresholds
    high_confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Accept immediately at or above this threshold"
    )
    mid_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Can trigger clarification at or above this threshold"
    )

    # Clarification settings
    enable_clarification: bool = Field(
        default=True,
        description="Whether to enable clarification for mid-confidence results"
    )
    max_clarification_rounds: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum clarification questions per conversation"
    )

    # Sub-configurations
    keyword: KeywordConfig = Field(
        default_factory=KeywordConfig,
        description="Keyword classification settings"
    )
    cache: CacheConfig = Field(
        default_factory=CacheConfig,
        description="Result cache settings"
    )
    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="LLM fallback settings"
    )

    # Fallback defaults
    fallback_intent: str = Field(
        default="chat",
        description="Default intent when all strategies fail"
    )
    fallback_confidence: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Confidence for fallback results"
    )

    model_config = {"extra": "allow"}

    def is_high_confidence(self, confidence: float) -> bool:
        """Check if confidence meets high threshold.

        Args:
            confidence: Confidence score to check

        Returns:
            True if confidence >= high_confidence
        """
        return confidence >= self.high_confidence

    def is_mid_confidence(self, confidence: float) -> bool:
        """Check if confidence is in mid range.

        Args:
            confidence: Confidence score to check

        Returns:
            True if mid_confidence <= confidence < high_confidence
        """
        return self.mid_confidence <= confidence < self.high_confidence

    def is_low_confidence(self, confidence: float) -> bool:
        """Check if confidence is below mid threshold.

        Args:
            confidence: Confidence score to check

        Returns:
            True if confidence < mid_confidence
        """
        return confidence < self.mid_confidence

    def can_clarify(self, clarification_count: int) -> bool:
        """Check if clarification is still allowed.

        Args:
            clarification_count: Current number of clarification rounds

        Returns:
            True if clarification enabled and under max rounds
        """
        return self.enable_clarification and clarification_count < self.max_clarification_rounds

    def should_use_keyword_only(
        self, message: str, has_image: bool, is_complex: bool = False
    ) -> bool:
        """Determine if keyword-only classification should be used.

        Args:
            message: User message
            has_image: Whether message contains an image
            is_complex: Whether request is externally marked as complex

        Returns:
            True if keyword-only path should be attempted
        """
        if has_image or is_complex:
            return False

        # Check length
        if len(message) > self.keyword.max_length:
            return False

        # Check for complex words
        for word in self.keyword.complex_words:
            if word in message:
                return False

        return True
