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


class TestSTARStandards:
    """验证记忆检索是否符合STAR标准"""

    @pytest.mark.asyncio
    async def test_hybrid_scoring_formula(self, mock_repo):
        """测试混合评分公式：0.6×向量 + 0.2×时间 + 0.2×对话"""
        from app.core.memory.config import MemoryConfig

        config = MemoryConfig()
        now = time.time()
        conv_id = uuid4()

        mock_repo._results = [{
            "content": "用户喜欢北京旅游",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(conv_id),  # 同一对话
                "created_at": now,  # 新记忆
                "memory_type": "preference",
            },
            "score": 0.9,  # 高向量相似度
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo, config=config)

        memories = await retriever.retrieve(
            query="我想去北京",
            user_id="test_user",
            conversation_id=conv_id,
        )

        assert len(memories) == 1
        # 手动计算预期分数：
        # vector = 0.9, time_decay ≈ 1.0, recency = 1.0 (同一对话)
        # final = 0.6*0.9 + 0.2*1.0 + 0.2*1.0 = 0.54 + 0.2 + 0.2 = 0.94
        expected = 0.6 * 0.9 + 0.2 * 1.0 + 0.2 * 1.0
        assert abs(memories[0].importance - expected) < 0.01

    @pytest.mark.asyncio
    async def test_time_decay_30day_halflife(self, mock_repo):
        """测试时间衰减：30天半衰期"""
        from app.core.memory.config import MemoryConfig

        config = MemoryConfig()
        now = time.time()
        conv_id = uuid4()

        # 测试30天前的记忆
        old_time = now - (30 * 86400)
        mock_repo._results = [{
            "content": "30天前的记忆",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "created_at": old_time,
                "memory_type": "preference",
            },
            "score": 1.0,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo, config=config)

        memories = await retriever.retrieve(
            query="test",
            user_id="test_user",
            conversation_id=conv_id,
        )

        # 30天后：time_decay = 0.5^(30/30) = 0.5
        # final = 0.6*1.0 + 0.2*0.5 + 0.2*0.3 = 0.6 + 0.1 + 0.06 = 0.76
        expected = 0.6 * 1.0 + 0.2 * 0.5 + 0.2 * 0.3
        assert abs(memories[0].importance - expected) < 0.01

    def test_weights_sum_to_one(self):
        """测试权重总和为1.0"""
        from app.core.memory.config import MemoryConfig

        config = MemoryConfig()
        total = config.vector_weight + config.time_decay_weight + config.recency_weight

        assert abs(total - 1.0) < 0.001, \
            f"权重总和应为1.0，实际为{total}"

        # 验证具体权重值
        assert config.vector_weight == 0.6, "向量权重应为0.6"
        assert config.time_decay_weight == 0.2, "时间衰减权重应为0.2"
        assert config.recency_weight == 0.2, "对话新颖性权重应为0.2"

    def test_scenario_thresholds(self):
        """测试场景感知阈值"""
        from app.core.memory.config import MemoryConfig, RetrievalScenario

        config = MemoryConfig()

        # 严格场景：0.7
        strict_threshold = config.retrieval.get_threshold(RetrievalScenario.STRICT)
        assert strict_threshold == 0.7, f"严格场景阈值应为0.7，实际为{strict_threshold}"

        # 普通场景：0.6
        normal_threshold = config.retrieval.get_threshold(RetrievalScenario.NORMAL)
        assert normal_threshold == 0.6, f"普通场景阈值应为0.6，实际为{normal_threshold}"

        # 模糊场景：0.5
        fuzzy_threshold = config.retrieval.get_threshold(RetrievalScenario.FUZZY)
        assert fuzzy_threshold == 0.5, f"模糊场景阈值应为0.5，实际为{fuzzy_threshold}"

    def test_time_decay_formula(self):
        """测试时间衰减公式：time_decay = 0.5^(days/30)"""
        from app.core.memory.config import MemoryConfig

        config = MemoryConfig()
        halflife = config.time_decay_halflife  # 30天

        # 测试不同天数
        test_cases = [
            (1, 0.977),   # 1天：0.5^(1/30) ≈ 0.977
            (7, 0.846),   # 7天：0.5^(7/30) ≈ 0.846
            (30, 0.5),    # 30天：0.5^(30/30) = 0.5
            (60, 0.25),   # 60天：0.5^(60/30) = 0.25
        ]

        for days, expected_min in test_cases:
            decay = pow(0.5, days / halflife)
            assert decay >= expected_min - 0.01, \
                f"{days}天衰减计算错误：{decay:.3f} < {expected_min}"
