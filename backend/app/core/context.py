"""RequestContext - Shared context object across all modules.

Provides a unified context that flows through:
- IntentRouter
- PromptService
- MemoryService
- QueryEngine

NOTE: SlotResult is imported from existing intent.slot_extractor to avoid duplication.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.core.intent.slot_extractor import SlotResult


class IntentType(str):
    """Intent types (extends existing)"""
    # Re-export existing intent types
    ITINERARY = "itinerary"
    QUERY = "query"
    CHAT = "chat"
    IMAGE = "image"
    # New intent types
    CLARIFICATION = "clarification"
    FALLBACK = "fallback"


# Intent result data class
class IntentResult(BaseModel):
    """Intent classification result.

    Attributes:
        intent: Intent type (itinerary, query, image, chat)
        confidence: Confidence score 0.0-1.0
        method: Classification method (cache, rule, llm, attachment, default)
        reasoning: Optional explanation of classification
        need_tool: Whether tool calling is needed
        clarification: Optional clarification info
        strategy: Name of the strategy that produced this result
    """
    intent: str
    confidence: float
    method: str = "unknown"
    reasoning: Optional[str] = None
    need_tool: bool = False
    clarification: Optional[dict] = None
    strategy: Optional[str] = None  # Name of the strategy that produced this result


class RequestContext(BaseModel):
    """Request context - flows through all modules

    Carries:
    - Core request info (message, user_id, conversation_id)
    - Extracted info (slots, history, memories)
    - State (clarification_count, max_tokens)
    - Tool results
    """

    # Core info
    message: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None

    # Extracted info
    slots: Optional[SlotResult] = None
    history: List[Dict[str, str]] = []

    # Memory data
    memories: List[Any] = []  # List[MemoryItem]

    # Clarification state
    clarification_count: int = 0
    max_clarification_rounds: int = 2

    # Configuration
    max_tokens: int = 16000

    # Tool results
    tool_results: Dict[str, Any] = {}

    # Image flag - whether the message contains an image
    has_image: bool = False

    # Complexity flag - whether the request is complex
    is_complex: bool = False

    def update(self, **kwargs) -> "RequestContext":
        """Create updated context copy"""
        return self.model_copy(update=kwargs)
