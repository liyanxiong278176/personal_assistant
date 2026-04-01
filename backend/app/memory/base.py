"""Base types and definitions for memory system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID


class MemoryType(str, Enum):
    """Types of memory entries."""

    FACT = "fact"  # Factual information (destination, dates, budget)
    PREFERENCE = "preference"  # User preferences
    INTENT = "intent"  # User intentions
    CONSTRAINT = "constraint"  # Constraints (budget, time)
    EMOTION = "emotion"  # User emotions/feelings
    STATE = "state"  # Conversation state


@dataclass
class ExtractedMemory:
    """A memory extracted from conversation."""

    type: MemoryType
    content: str
    structured_data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5  # 0.0 to 1.0
    importance: float = 0.5  # 0.0 to 1.0
    source_message_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "type": self.type.value,
            "content": self.content,
            "structured_data": self.structured_data,
            "confidence": self.confidence,
            "importance": self.importance,
            "source_message_id": self.source_message_id,
        }


@dataclass
class MemoryContext:
    """Context for LLM requests with memory."""

    system_prompt: str
    long_term_memory: list[dict] = field(default_factory=list)
    short_term_memory: list[dict] = field(default_factory=list)
    working_memory: list[dict] = field(default_factory=list)
    current_message: str = ""

    def to_llm_messages(self) -> list[dict[str, str]]:
        """Convert to LLM message format."""
        messages = [{"role": "system", "content": self.system_prompt}]

        if self.long_term_memory:
            memory_text = "\n".join([
                f"- {m['content']}" for m in self.long_term_memory
            ])
            messages.append({
                "role": "system",
                "content": f"用户画像和长期偏好:\n{memory_text}"
            })

        if self.short_term_memory:
            memory_text = "\n".join([
                f"- [{m['type']}] {m['content']}" for m in self.short_term_memory
            ])
            messages.append({
                "role": "system",
                "content": f"当前对话关键信息:\n{memory_text}"
            })

        messages.extend(self.working_memory)

        if self.current_message:
            messages.append({"role": "user", "content": self.current_message})

        return messages
