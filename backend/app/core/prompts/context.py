"""TemplateContext - Template rendering context dataclass"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TemplateContext:
    """Template rendering context - encapsulates all variables for template rendering

    Separated from RequestContext because:
    1. RequestContext = user request input (message, user_id)
    2. TemplateContext = template rendering data (slots, tool_results)
    3. Follows single responsibility principle and temporal ordering
    """

    intent: str
    slots: Any  # SlotResult from app.core.intent.slot_extractor
    tool_results: Dict[str, Any]
    context: str  # Full context built by Stage 5
    user_message: str
    memories: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None

    def to_template_vars(self) -> Dict[str, Any]:
        """Convert to template variable dictionary for PromptService

        Returns:
            Dict with all template variables (empty strings for missing fields)
        """
        return {
            "user_message": self.user_message,
            "slots": self.slots,
            "tool_results": self.tool_results,
            "memories": self.memories or "",
            "context": self.context,
            "user_id": self.user_id or "anonymous",
            "conversation_id": self.conversation_id or "",
        }
