# backend/app/core/memory/conflict_resolver.py
"""Memory conflict detection and resolution."""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.core.memory.hierarchy import MemoryItem


class MemoryOperation(Enum):
    """Memory operation types."""
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"


@dataclass
class ConflictResolution:
    """Conflict resolution result."""
    operation: MemoryOperation
    existing_item: Optional["MemoryItem"] = None
    new_item: Optional["MemoryItem"] = None
    reason: str = ""
    similarity: float = 0.0
    fallback_used: bool = False


class MemoryConflictResolver:
    """Memory conflict resolver with LLM confirmation."""

    SEMANTIC_THRESHOLD = 0.85
    FALLBACK_ON_SIMILARITY_ABOVE = 0.90
    FALLBACK_ON_SIMILARITY_BELOW = 0.80

    def __init__(self, embedding_client, llm_client):
        self._embedding = embedding_client
        self._llm = llm_client

    async def resolve(
        self,
        new_memory: "MemoryItem",
        existing_memories: List["MemoryItem"],
    ) -> ConflictResolution:
        """Resolve memory conflict."""
        for existing in existing_memories:
            similarity = await self._compute_similarity_safe(new_memory, existing)

            if similarity >= self.SEMANTIC_THRESHOLD:
                try:
                    operation = await self._llm_confirm_operation_safe(
                        new_memory, existing
                    )

                    return ConflictResolution(
                        operation=operation,
                        existing_item=existing,
                        new_item=new_memory,
                        similarity=similarity,
                        reason=f"相似度{similarity:.2f}，LLM确认为{operation.value}"
                    )
                except Exception as e:
                    logger.warning(f"[ConflictResolver] LLM确认失败: {e}")
                    return self._fallback_resolution(new_memory, existing, similarity)

        return ConflictResolution(
            operation=MemoryOperation.ADD,
            new_item=new_memory,
            reason="全新信息，无冲突"
        )

    async def _compute_similarity_safe(
        self,
        item1: "MemoryItem",
        item2: "MemoryItem"
    ) -> float:
        """Compute similarity in thread pool to avoid blocking."""
        def _sync_compute():
            emb1 = self._embedding.embed_query(item1.content)
            emb2 = self._embedding.embed_query(item2.content)

            import numpy as np
            return np.dot(emb1, emb2) / (
                np.linalg.norm(emb1) * np.linalg.norm(emb2)
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_compute)

    async def _llm_confirm_operation_safe(
        self,
        new_item: "MemoryItem",
        existing_item: "MemoryItem"
    ) -> MemoryOperation:
        """LLM confirmation with timeout and error handling."""
        prompt = f"""
判断以下两句话的关系：

旧信息: {existing_item.content}
新信息: {new_item.content}

请回答以下选项之一：
- UPDATE: 新信息是对旧信息的更新或修正
- NOOP: 新信息与旧信息一致或重复
- DELETE: 新信息表示旧信息已失效

只回答选项名称，不要解释。
"""

        try:
            response = await asyncio.wait_for(
                self._llm.generate(prompt),
                timeout=5.0
            )

            # Use strict return value matching to prevent misidentification
            response = response.strip().upper()

            # Extract first word and match exactly
            first_word = response.split()[0] if response.split() else response

            operation_map = {
                "UPDATE": MemoryOperation.UPDATE,
                "DELETE": MemoryOperation.DELETE,
                "NOOP": MemoryOperation.NOOP,
                "ADD": MemoryOperation.ADD,
            }

            return operation_map.get(first_word, MemoryOperation.NOOP)

        except (asyncio.TimeoutError, Exception) as e:
            raise Exception(f"LLM确认失败: {e}")

    def _fallback_resolution(
        self,
        new_item: "MemoryItem",
        existing_item: "MemoryItem",
        similarity: float
    ) -> ConflictResolution:
        """Fallback resolution when LLM fails."""
        if similarity >= self.FALLBACK_ON_SIMILARITY_ABOVE:
            return ConflictResolution(
                operation=MemoryOperation.UPDATE,
                existing_item=existing_item,
                new_item=new_item,
                similarity=similarity,
                reason=f"LLM失败，相似度{similarity:.2f}判定为UPDATE",
                fallback_used=True
            )
        elif similarity <= self.FALLBACK_ON_SIMILARITY_BELOW:
            return ConflictResolution(
                operation=MemoryOperation.ADD,
                new_item=new_item,
                similarity=similarity,
                reason=f"LLM失败，相似度{similarity:.2f}判定为ADD",
                fallback_used=True
            )
        else:
            return ConflictResolution(
                operation=MemoryOperation.NOOP,
                existing_item=existing_item,
                new_item=new_item,
                similarity=similarity,
                reason=f"LLM失败，相似度{similarity:.2f}保守处理为NOOP",
                fallback_used=True
            )
