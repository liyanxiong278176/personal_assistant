# backend/app/core/memory/conflict_resolver.py
"""Memory conflict detection and resolution."""

import asyncio
import logging
import time
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
    OVERWRITE = "overwrite"  # v2.3新增：完全替换
    CLEAR = "clear"  # v2.3新增：批量清除
    COMPLEMENT = "complement"  # 互补合并：新旧记忆互补，构建完整记忆


@dataclass
class ConflictResolution:
    """Conflict resolution result (unified interface for v2.1)."""
    operation: MemoryOperation = MemoryOperation.ADD
    existing_item: Optional["MemoryItem"] = None
    new_item: Optional["MemoryItem"] = None
    reason: str = ""
    similarity: float = 0.0
    fallback_used: bool = False
    # v2.1 additional fields for hierarchy.py compatibility
    has_conflict: bool = False
    resolved_item: Optional["MemoryItem"] = None
    # v2.3新增：CLEAR操作的类型范围
    clear_type: Optional["MemoryType"] = None


class MemoryConflictResolver:
    """Memory conflict resolver with LLM confirmation."""

    SEMANTIC_THRESHOLD = 0.85
    FALLBACK_ON_SIMILARITY_ABOVE = 0.90
    FALLBACK_ON_SIMILARITY_BELOW = 0.80

    def __init__(self, embedding_client, llm_client):
        self._embedding = embedding_client
        self._llm = llm_client

    async def check_conflict(
        self,
        new_item: "MemoryItem",
        existing_memories: List["MemoryItem"],
    ) -> ConflictResolution:
        """Check if new item conflicts with existing memories.

        Fills has_conflict and resolved_item for hierarchy.py compatibility.
        v2.3: OVERWRITE和CLEAR也视为冲突。
        """
        result = await self.resolve(new_item, existing_memories)
        result.has_conflict = result.operation in (
            MemoryOperation.UPDATE,
            MemoryOperation.DELETE,
            MemoryOperation.NOOP,
            MemoryOperation.OVERWRITE,  # v2.3新增
            MemoryOperation.CLEAR,  # v2.3新���
            MemoryOperation.COMPLEMENT,  # 互补合并
        )
        result.resolved_item = self._apply_resolution(result)
        return result

    def _apply_resolution(self, result: ConflictResolution) -> Optional["MemoryItem"]:
        """Apply resolution and return the item to store."""
        if result.operation == MemoryOperation.ADD:
            return result.new_item
        elif result.operation == MemoryOperation.UPDATE:
            # Merge: keep existing metadata, update content
            if result.existing_item and result.new_item:
                merged = result.existing_item
                merged.content = result.new_item.content
                merged.metadata.update(result.new_item.metadata or {})
                return merged
            return result.new_item
        elif result.operation == MemoryOperation.OVERWRITE:
            # v2.3新增：完全替换，返回新item
            return result.new_item
        elif result.operation == MemoryOperation.CLEAR:
            # v2.3新增：批量清除，返回None
            return None
        elif result.operation == MemoryOperation.COMPLEMENT:
            # 互补合并：新旧记忆互补，构建完整记忆
            if result.existing_item and result.new_item:
                return self._merge_complementary(result.existing_item, result.new_item)
            return result.new_item
        elif result.operation == MemoryOperation.DELETE:
            return None
        else:  # NOOP
            return result.existing_item

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
                    operation, clear_type = await self._llm_confirm_operation_safe(
                        new_memory, existing
                    )

                    return ConflictResolution(
                        operation=operation,
                        existing_item=existing,
                        new_item=new_memory,
                        similarity=similarity,
                        reason=f"相似度{similarity:.2f}，LLM确认为{operation.value}",
                        clear_type=clear_type
                    )
                except Exception as e:
                    logger.warning(f"[ConflictResolver] LLM确认失败: {e}")
                    return self._fallback_resolution(new_memory, existing, similarity)

        return ConflictResolution(
            operation=MemoryOperation.ADD,
            new_item=new_memory,
            reason="全新信息，无冲突"
        )

    def _merge_complementary(
        self,
        existing: "MemoryItem",
        new: "MemoryItem"
    ) -> "MemoryItem":
        """Merge complementary memories into a complete memory.

        互补合并策略：
        - 合并内容：保留两部分的完整信息
        - 合并元数据：取并集
        - 强化记忆：提升记忆强度和重要性
        """
        from app.core.memory.hierarchy import MemoryItem

        # 智能合并内容（去重拼接）
        existing_content = existing.content.strip()
        new_content = new.content.strip()

        # 如果新内容已包含在旧内容中，返回旧记忆
        if new_content in existing_content:
            merged_content = existing_content
        # 如果旧内容已包含在新内容中，返回新记忆
        elif existing_content in new_content:
            merged_content = new_content
        # 否则拼接，使用分隔符
        else:
            # 尝试找到合适的连接词
            separators = ["，", "；", "。", "；", ", "]
            merged_content = existing_content
            for sep in separators:
                if not existing_content.endswith(sep):
                    merged_content = existing_content + sep + new_content
                    break
            else:
                merged_content = f"{existing_content}；{new_content}"

        # 合并 metadata
        merged_metadata = existing.metadata.copy()
        merged_metadata.update(new.metadata or {})
        merged_metadata["complementary_merge"] = True
        merged_metadata["merged_at"] = time.time()

        # 合并重要性（取最大值并略微提升）
        merged_importance = max(existing.importance, new.importance)
        merged_importance = min(merged_importance + 0.05, 1.0)

        # 合并置信度
        merged_confidence = max(existing.confidence, new.confidence)

        return MemoryItem(
            content=merged_content,
            level=existing.level,
            memory_type=existing.memory_type,
            metadata=merged_metadata,
            confidence=merged_confidence,
            importance=merged_importance,
            created_at=existing.created_at,  # 保留原始创建时间
            item_id=existing.item_id,  # 保留原有 ID
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

    def _parse_llm_response(
        self,
        response: str,
        existing_item: "MemoryItem"
    ) -> tuple[MemoryOperation, Optional["MemoryType"]]:
        """Parse LLM response to get operation and optional clear type.

        v2.3新增：支持OVERWRITE和CLEAR:类型格式

        Returns:
            (operation, clear_type) tuple
        """
        from app.core.memory.hierarchy import MemoryType

        response = response.strip().upper()

        # CLEAR response may include type: "CLEAR:PREFERENCE" or just "CLEAR"
        if response.startswith("CLEAR"):
            parts = response.split(":")
            if len(parts) > 1:
                try:
                    clear_type = MemoryType(parts[1].lower())
                except ValueError:
                    clear_type = existing_item.memory_type
            else:
                clear_type = existing_item.memory_type
            return (MemoryOperation.CLEAR, clear_type)

        # Other operations
        operation_map = {
            "UPDATE": MemoryOperation.UPDATE,
            "OVERWRITE": MemoryOperation.OVERWRITE,
            "DELETE": MemoryOperation.DELETE,
            "NOOP": MemoryOperation.NOOP,
            "ADD": MemoryOperation.ADD,
            "COMPLEMENT": MemoryOperation.COMPLEMENT,
        }

        first_word = response.split()[0] if response.split() else response
        return (operation_map.get(first_word, MemoryOperation.NOOP), None)

    async def _llm_confirm_operation_safe(
        self,
        new_item: "MemoryItem",
        existing_item: "MemoryItem"
    ) -> tuple[MemoryOperation, Optional["MemoryType"]]:
        """LLM confirmation with timeout and error handling.

        v2.3新增：支持OVERWRITE和CLEAR:类型格式

        Returns:
            (operation, clear_type) tuple
        """
        prompt = f"""
判断以下两句话的关系：

旧信息: {existing_item.content}
新信息: {new_item.content}

请回答以下选项之一：
- UPDATE: 新信息是对旧信息的更新或修正
- OVERWRITE: 新信息完全替换旧信息（v2.3新增）
- NOOP: 新信息与旧信息一致或重复
- DELETE: 新信息表示旧信息已失效
- CLEAR: 清除某类型的所有记忆（格式: CLEAR:类型，如CLEAR:PREFERENCE，或仅CLEAR）
- COMPLEMENT: 新信息与旧信息互补，需要合并成完整记忆

只回答选项名称，不要解释。
"""

        try:
            response = await asyncio.wait_for(
                self._llm.generate(prompt),
                timeout=5.0
            )

            return self._parse_llm_response(response, existing_item)

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
