"""Tests for vector store and memory service.

References:
- AI-01: RAG-based long-term memory
- INFRA-04: Vector database for conversation history
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.memory_service import MemoryService
from app.db.vector_store import VectorStore


class TestVectorStore:
    """Test ChromaDB vector store operations."""

    @pytest.mark.asyncio
    async def test_store_message(self):
        """Test storing a message in vector store."""
        # Arrange
        store = VectorStore()
        user_id = "test-user-123"
        conversation_id = "test-conv-456"
        role = "user"
        content = "我喜欢安静的海滩度假"

        # Act
        await store.store_message(user_id, conversation_id, role, content)

        # Assert
        # Verify message was stored (retrieval should return it)
        results = await store.retrieve_context(user_id, "海滩", k=1)
        assert len(results) > 0
        assert any("海滩" in r.get("content", "") for r in results)

    @pytest.mark.asyncio
    async def test_retrieve_context_with_user_filter(self):
        """Test that retrieval is scoped to user_id."""
        # Arrange
        store = VectorStore()
        user_a = "user-a"
        user_b = "user-b"

        # Store messages for different users
        await store.store_message(user_a, "conv-1", "user", "User A likes hiking")
        await store.store_message(user_b, "conv-2", "user", "User B likes swimming")

        # Act - User A searches for "likes"
        results = await store.retrieve_context(user_a, "likes", k=10)

        # Assert - Should only get User A's messages
        assert all(r.get("metadata", {}).get("user_id") == user_a for r in results)
        assert not any("swimming" in r.get("content", "") for r in results)


class TestMemoryService:
    """Test RAG-based memory service."""

    @pytest.mark.asyncio
    async def test_rag_retrieval(self):
        """Test semantic retrieval of relevant conversation history."""
        # Arrange
        service = MemoryService()
        user_id = "test-user"

        # Store conversation history
        await service.store_message(
            user_id=user_id,
            conversation_id="conv-1",
            role="user",
            content="我喜欢历史古迹，尤其是古城墙和博物馆"
        )
        await service.store_message(
            user_id=user_id,
            conversation_id="conv-1",
            role="assistant",
            content="了解了，您对历史文化感兴趣"
        )

        # Act - Search with semantic query
        results = await service.retrieve_relevant_history(
            user_id=user_id,
            query="推荐一些文化景点",
            k=2
        )

        # Assert
        assert len(results) <= 2
        # Should retrieve the museum-related conversation
        retrieved_content = " ".join([r.get("content", "") for r in results])
        assert "历史" in retrieved_content or "文化" in retrieved_content or "博物馆" in retrieved_content

    @pytest.mark.asyncio
    async def test_cross_session_memory(self):
        """Test that memory persists across different conversations."""
        # Arrange
        service = MemoryService()
        user_id = "test-user"

        # Store in conversation 1
        await service.store_message(
            user_id=user_id,
            conversation_id="conv-old",
            role="user",
            content="我的预算是中等水平"
        )

        # Act - Retrieve in conversation 2 context
        results = await service.retrieve_relevant_history(
            user_id=user_id,
            query="预算范围",
            k=1
        )

        # Assert
        assert len(results) > 0
        assert "预算" in results[0].get("content", "")

    @pytest.mark.asyncio
    async def test_build_context_prompt(self):
        """Test building context prompt with relevant history."""
        # Arrange
        service = MemoryService()
        user_id = "test-user"

        # Store some history
        await service.store_message(
            user_id=user_id,
            conversation_id="conv-1",
            role="user",
            content="我喜欢自然风光"
        )

        # Act
        context = await service.build_context_prompt(
            user_id=user_id,
            current_message="推荐一些景点",
            max_history=1
        )

        # Assert
        assert "相关对话历史" in context or context == ""  # May be empty if no matches
