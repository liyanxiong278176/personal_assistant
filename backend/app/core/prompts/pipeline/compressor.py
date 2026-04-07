"""TokenCompressor - Compress prompts to fit within token budget

Provides budget management for prompts by estimating token count
and trimming from the end when the prompt exceeds the target ratio
of the maximum allowed tokens.

This is the final filter in the prompt processing pipeline.
"""

from typing import TYPE_CHECKING

from app.core.prompts.pipeline.base import IPromptFilter
from app.core.prompts.providers.base import PromptFilterResult

if TYPE_CHECKING:
    from app.core.context import RequestContext


class TokenCompressor(IPromptFilter):
    """Token budget compressor - trims prompts that exceed token limits

    Estimates token count using character count divided by chars_per_token,
    and trims from the end when the prompt exceeds context.max_tokens * target_ratio.

    Attributes:
        target_ratio: Fraction of max_tokens to use as the budget threshold (default 0.8)
        chars_per_token: Characters per token estimate (default 4)
    """

    def __init__(
        self,
        target_ratio: float = 0.8,
        chars_per_token: int = 4,
    ) -> None:
        """Initialize the token compressor.

        Args:
            target_ratio: Fraction of context.max_tokens to use as budget (0.0-1.0).
                          Default 0.8 reserves 20% headroom.
            chars_per_token: Characters per token for estimation. Default 4.
        """
        if not 0 < target_ratio <= 1:
            raise ValueError("target_ratio must be between 0 and 1 (exclusive of 0)")
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")

        self.target_ratio = target_ratio
        self.chars_per_token = chars_per_token

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Input text to estimate

        Returns:
            Estimated token count (integer, floor division)
        """
        return len(text) // self.chars_per_token

    async def process(
        self,
        prompt: str,
        context: "RequestContext",
    ) -> PromptFilterResult:
        """Process prompt, compressing if it exceeds token budget.

        Estimates tokens in the prompt and trims from the end if it exceeds
        context.max_tokens * target_ratio.

        Args:
            prompt: Input prompt text
            context: Request context containing max_tokens budget

        Returns:
            PromptFilterResult with compressed content and warning if trimmed
        """
        # Calculate budget based on target_ratio
        budget_chars = int(context.max_tokens * self.target_ratio) * self.chars_per_token

        # Check if compression is needed
        if len(prompt) <= budget_chars:
            return PromptFilterResult(
                success=True,
                content=prompt,
            )

        # Trim from the end to fit budget
        compressed = prompt[:budget_chars]

        return PromptFilterResult(
            success=True,
            content=compressed,
            warning=(
                f"Prompt trimmed from {len(prompt)} to {len(compressed)} characters "
                f"to fit token budget ({self._estimate_tokens(prompt)} -> "
                f"{self._estimate_tokens(compressed)} tokens)"
            ),
        )
