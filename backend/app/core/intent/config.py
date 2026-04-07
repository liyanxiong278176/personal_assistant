"""IntentRouter configuration

Defines confidence thresholds and behavior settings for intent classification routing.
"""

from typing import Optional

from pydantic import BaseModel, Field


class IntentRouterConfig(BaseModel):
    """Configuration for IntentRouter behavior.

    Attributes:
        high_confidence_threshold: Minimum confidence to accept classification immediately (default 0.9)
        mid_confidence_threshold: Minimum confidence to trigger clarification (default 0.7)
        max_clarification_rounds: Maximum number of clarification questions (default 2)
        enable_clarification: Whether to enable clarification flow (default True)
        rule_traffic_ratio: Target percentage of traffic handled by rule strategies (default 0.6)
        rule_hit_rate_threshold: Minimum rule strategy hit rate before triggering review (default 0.4)
    """

    high_confidence_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to accept classification immediately"
    )
    mid_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to trigger clarification flow"
    )
    max_clarification_rounds: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum number of clarification questions to ask"
    )
    enable_clarification: bool = Field(
        default=True,
        description="Whether to enable clarification flow for medium confidence"
    )
    rule_traffic_ratio: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Target percentage of traffic handled by rule strategies"
    )
    rule_hit_rate_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum rule strategy hit rate before triggering review"
    )

    model_config = {"extra": "allow"}

    def is_high_confidence(self, confidence: float) -> bool:
        """Check if confidence meets high threshold.

        Args:
            confidence: Confidence score to check

        Returns:
            True if confidence >= high_confidence_threshold
        """
        return confidence >= self.high_confidence_threshold

    def is_mid_confidence(self, confidence: float) -> bool:
        """Check if confidence meets medium threshold but not high.

        Args:
            confidence: Confidence score to check

        Returns:
            True if mid_confidence_threshold <= confidence < high_confidence_threshold
        """
        return (
            self.mid_confidence_threshold <= confidence < self.high_confidence_threshold
        )

    def is_low_confidence(self, confidence: float) -> bool:
        """Check if confidence is below medium threshold.

        Args:
            confidence: Confidence score to check

        Returns:
            True if confidence < mid_confidence_threshold
        """
        return confidence < self.mid_confidence_threshold

    def can_clarify(self, clarification_count: int) -> bool:
        """Check if clarification is still allowed.

        Args:
            clarification_count: Current number of clarification rounds

        Returns:
            True if clarification is enabled and under max rounds
        """
        return self.enable_clarification and clarification_count < self.max_clarification_rounds
