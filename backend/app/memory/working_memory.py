"""Working memory - recent messages in memory with token sliding window."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.db.postgres import Message

logger = logging.getLogger(__name__)


@dataclass
class WorkingMemory:
    """Working memory: recent conversation messages with token limit.

    Maintains the most recent messages within a token budget,
    trimming oldest messages when the limit is exceeded.
    """

    conversation_id: UUID
    messages: list[dict] = field(default_factory=list)
    max_tokens: int = 4000

    def add_message(self, role: str, content: str) -> None:
        """Add a message and trim if necessary.

        Args:
            role: Message role (user/assistant/system)
            content: Message content
        """
        self.messages.append({
            "role": role,
            "content": content,
        })
        self._trim_to_token_limit()

    def _trim_to_token_limit(self) -> None:
        """Remove oldest messages to stay within token limit."""
        total_tokens = self._estimate_tokens()
        while total_tokens > self.max_tokens and len(self.messages) > 2:
            # Remove oldest message (keep at least system + last message)
            removed = self.messages.pop(0)
            total_tokens -= self._estimate_message_tokens(removed)
            logger.debug(
                f"[WorkingMemory] Trimmed message: {removed['role']}, "
                f"tokens: {self._estimate_message_tokens(removed)}"
            )

    def _estimate_tokens(self) -> int:
        """Estimate total tokens in all messages."""
        return sum(self._estimate_message_tokens(m) for m in self.messages)

    def _estimate_message_tokens(self, message: dict) -> int:
        """Rough token estimation (1 token ≈ 4 characters for Chinese)."""
        return len(message["content"]) // 4 + 10  # +10 for overhead

    def to_llm_format(self) -> list[dict]:
        """Convert to LLM message format."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.messages
        ]

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()

    def size(self) -> int:
        """Return number of messages."""
        return len(self.messages)

    def token_count(self) -> int:
        """Return estimated token count."""
        return self._estimate_tokens()
