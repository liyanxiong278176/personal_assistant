"""Ebbinghaus forgetting curve with retrieval reinforcement."""
import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import List

from app.core.memory.hierarchy import MemoryItem

logger = logging.getLogger(__name__)


@dataclass
class MemoryStrength:
    """Memory strength tracker (stored in metadata)."""
    initial_strength: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    decay_factor: float = 30.0  # Half-life in days

    def get_current_strength(self) -> float:
        """Calculate current memory strength.

        Formula: strength = initial x e^(-age/halflife) x log(1+access_count) x recency
        """
        age_days = (time.time() - self.created_at) / 86400
        time_decay = math.exp(-age_days / self.decay_factor)

        access_bonus = math.log(1 + self.access_count)

        recency_days = (time.time() - self.last_accessed) / 86400
        recency_bonus = math.exp(-recency_days / 7)  # 7-day decay

        return min(
            self.initial_strength * time_decay * access_bonus * recency_bonus,
            1.0
        )

    def reinforce(self):
        """Reinforce memory on retrieval - each access strengthens memory."""
        self.access_count += 1
        self.last_accessed = time.time()
        # Initial strength increases with each access, capped at 1.0
        self.initial_strength = min(self.initial_strength + 0.10, 1.0)

    def to_dict(self) -> dict:
        """Serialize to dict for metadata storage."""
        return {
            "initial_strength": self.initial_strength,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "decay_factor": self.decay_factor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryStrength":
        """Deserialize from metadata storage."""
        return cls(**data)


class ForgettingCurveManager:
    """Forgetting curve manager with retrieval reinforcement."""

    FORGETTING_THRESHOLD = 0.3

    def __init__(self, semantic_repo):
        """Initialize forgetting curve manager.

        Args:
            semantic_repo: SemanticRepository for metadata persistence
        """
        self._semantic_repo = semantic_repo

    def is_forgotten(self, memory_or_strength) -> bool:
        """Check if memory is forgotten (strength < threshold).

        Accepts either a MemoryItem or a MemoryStrength object.
        """
        if isinstance(memory_or_strength, MemoryStrength):
            strength = memory_or_strength
        else:
            strength = self._get_strength(memory_or_strength)
        return strength.get_current_strength() < self.FORGETTING_THRESHOLD

    async def filter_active(self, memories: List[dict]) -> List[dict]:
        """Filter out forgotten memories from search results.

        Args:
            memories: List of search result dicts from semantic_repo.search_similar

        Returns:
            Active (non-forgotten) memories
        """
        active = []
        forgotten_count = 0

        for mem in memories:
            strength = self._get_strength_from_result(mem)
            if strength.get_current_strength() >= self.FORGETTING_THRESHOLD:
                active.append(mem)
            else:
                forgotten_count += 1

        if forgotten_count > 0:
            logger.info(
                f"[ForgettingCurve] Filtered {forgotten_count}/{len(memories)} "
                f"forgotten memories"
            )

        return active

    async def reinforce_memories(self, memories: List[dict]) -> None:
        """Reinforce memories and persist their updated strength.

        Args:
            memories: List of search result dicts
        """
        for mem in memories:
            item_id = mem.get("id", "")
            if not item_id:
                continue

            try:
                strength = self._get_strength_from_result(mem)
                strength.reinforce()

                await self._semantic_repo.update_metadata(
                    item_id,
                    {"strength": strength.to_dict()}
                )
            except Exception as e:
                logger.warning(f"[ForgettingCurve] Failed to reinforce {item_id}: {e}")

    def _get_strength(self, memory: MemoryItem) -> MemoryStrength:
        """Get or create MemoryStrength from a MemoryItem.

        MemoryItem.created_at is always a datetime object (hierarchy.py:66).
        """
        if "strength" in memory.metadata:
            return MemoryStrength.from_dict(memory.metadata["strength"])

        return MemoryStrength(
            initial_strength=memory.importance,
            created_at=memory.created_at.timestamp()
        )

    def _get_strength_from_result(self, result: dict) -> MemoryStrength:
        """Get or create MemoryStrength from a search result dict."""
        metadata = result.get("metadata", {})
        if "strength" in metadata:
            return MemoryStrength.from_dict(metadata["strength"])

        created_at = metadata.get("created_at", time.time())
        importance = metadata.get("importance", 0.5)

        # created_at might be a timestamp (float) from metadata
        created_ts = float(created_at) if created_at else time.time()

        return MemoryStrength(
            initial_strength=importance,
            created_at=created_ts
        )
