"""Tests for hybrid memory retrieval."""
import asyncio
import pytest
import time
from uuid import uuid4

from app.core.memory.retrieval import HybridRetriever
from app.core.memory.hierarchy import MemoryLevel, MemoryType


class MockSemanticRepository:
    """Mock semantic repository for testing."""

    def __init__(self, results=None):
        self._results = results or []

    async def search_similar(self, query_embedding, user_id, n_results=10):
        return self._results[:n_results]

    async def add(self, content, embedding, metadata):
        return "test_id"

    async def search(self, *args, **kwargs):
        return []

    async def get_by_type(self, user_id, memory_type, limit=20):
        return []


@pytest.fixture
def mock_repo():
    return MockSemanticRepository()


@pytest.fixture
async def retriever(mock_repo):
    return HybridRetriever(semantic_repo=mock_repo)


class TestHybridRetriever:
    """Test hybrid retrieval scoring."""

    @pytest.mark.asyncio
    async def test_empty_results(self, retriever):
        memories = await retriever.retrieve(
            query="test query",
            user_id="test_user",
            conversation_id=uuid4(),
        )
        assert memories == []

    @pytest.mark.asyncio
    async def test_vector_score_weight(self, mock_repo):
        now = time.time()

        mock_repo._results = [{
            "content": "test memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "created_at": now,
                "memory_type": "preference",
            },
            "score": 0.8,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)
        conv_id = uuid4()

        memories = await retriever.retrieve(
            query="test",
            user_id="test_user",
            conversation_id=conv_id,
        )

        assert len(memories) == 1
        # 0.6 * 0.8 + 0.2 * 1.0 + 0.2 * 0.3 ≈ 0.74
        assert 0.7 < memories[0].importance < 0.8

    @pytest.mark.asyncio
    async def test_time_decay_calculation(self, mock_repo):
        now = time.time()
        old_time = now - (30 * 86400)  # 30 days ago

        mock_repo._results = [{
            "content": "old memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "created_at": old_time,
                "memory_type": "preference",
            },
            "score": 1.0,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)
        conv_id = uuid4()

        memories = await retriever.retrieve(
            query="test",
            user_id="test_user",
            conversation_id=conv_id,
        )

        # 0.6*1.0 + 0.2*0.5 + 0.2*0.3 = 0.76
        assert 0.75 < memories[0].importance < 0.77

    @pytest.mark.asyncio
    async def test_same_conversation_boost(self, mock_repo):
        conv_id = uuid4()
        now = time.time()

        mock_repo._results = [{
            "content": "same conv memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(conv_id),
                "created_at": now,
                "memory_type": "preference",
            },
            "score": 0.5,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)

        memories = await retriever.retrieve(
            query="test",
            user_id="test_user",
            conversation_id=conv_id,
        )

        # 0.6*0.5 + 0.2*1.0 + 0.2*1.0 = 0.7
        assert 0.69 < memories[0].importance < 0.71
