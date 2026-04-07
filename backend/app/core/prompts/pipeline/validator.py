"""Validator - Ensure required variables are present in prompts

Implements IPromptFilter to check that all required variables
have been injected into the prompt before sending to LLM.

This helps catch missing template variables early in the pipeline.
"""

import logging
import re
from typing import TYPE_CHECKING, List, Optional, Set

from app.core.prompts.pipeline.base import IPromptFilter
from app.core.prompts.providers.base import PromptFilterResult

if TYPE_CHECKING:
    from app.core.context import RequestContext

logger = logging.getLogger(__name__)


class Validator(IPromptFilter):
    """Validator filter - ensures required variables are present

    Checks that template placeholders like {variable} have been
    replaced with actual values. Unreplaced placeholders indicate
    missing variable injection.

    Example:
        validator = Validator(required={"user_message"})
        result = await validator.process(prompt, context)
    """

    # Pattern to find template placeholders: {variable_name}
    PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")

    def __init__(
        self,
        required: Optional[Set[str]] = None,
        allow_empty: bool = False,
    ):
        """Initialize validator

        Args:
            required: Set of required variable names that must be present.
                     If None, all placeholders must be replaced.
            allow_empty: If True, empty values are acceptable (e.g., {slots} with no slots)
        """
        self.required = required
        self.allow_empty = allow_empty
        logger.debug(f"[Validator] Initialized with required={required}, allow_empty={allow_empty}")

    def _find_placeholders(self, text: str) -> List[str]:
        """Find all template placeholders in text

        Args:
            text: Text to search for placeholders

        Returns:
            List of placeholder names found
        """
        return self.PLACEHOLDER_PATTERN.findall(text)

    async def process(
        self,
        prompt: str,
        context: "RequestContext",
    ) -> PromptFilterResult:
        """Validate that required variables are present

        Args:
            prompt: Prompt text to validate
            context: Request context

        Returns:
            PromptFilterResult indicating validation status
        """
        # Find all remaining placeholders
        placeholders = self._find_placeholders(prompt)

        if not placeholders:
            # No placeholders found - all variables injected
            return PromptFilterResult(success=True, content=prompt)

        # Check if any required variables are missing
        if self.required:
            missing = [p for p in self.required if p in placeholders]
            if missing:
                return PromptFilterResult(
                    success=False,
                    content=prompt,
                    error=f"Required variables not injected: {', '.join(missing)}",
                    should_fallback=True,
                )

        # If specific requirements not set, any placeholder is a problem
        # unless allow_empty is True
        if not self.allow_empty:
            # Filter out potentially acceptable empty placeholders
            # (e.g., {slots} when no slots were extracted)
            acceptable_empty = self._get_acceptable_empty(context)
            problematic = [p for p in placeholders if p not in acceptable_empty]

            if problematic:
                return PromptFilterResult(
                    success=False,
                    content=prompt,
                    error=f"Template variables not replaced: {', '.join(problematic)}",
                    should_fallback=True,
                )

        # If we get here with placeholders, they must be acceptable empty ones
        # Replace them with empty strings for cleaner output
        if placeholders:
            for placeholder in placeholders:
                prompt = prompt.replace(f"{{{placeholder}}}", "")
            # Clean up extra whitespace
            prompt = re.sub(r"\n\s*\n", "\n\n", prompt)

        return PromptFilterResult(success=True, content=prompt)

    def _get_acceptable_empty(self, context: "RequestContext") -> Set[str]:
        """Get set of variable names that are acceptable when empty

        Args:
            context: Request context

        Returns:
            Set of acceptable empty variable names
        """
        acceptable = set()

        # {slots} is acceptable if we have no slots
        if not context.slots:
            acceptable.add("slots")

        # {memories} is acceptable if we have no memories
        if not context.memories:
            acceptable.add("memories")

        # {tool_results} is acceptable if we have no tool results
        if not context.tool_results:
            acceptable.add("tool_results")

        return acceptable
