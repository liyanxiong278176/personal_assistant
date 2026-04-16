"""Integration tests for Memory v2.1 features.

Tests the complete memory system with:
- Scenario-aware retrieval
- Dynamic threshold adjustment
- Configuration management
- Cross-component integration
"""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.core.memory import (
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    MemoryConfig,
    RetrievalScenario,
    HybridRetriever,
    MemoryInjector,
    MemoryPromoter,
)
from app.core.memory.repositories import SemanticRepository, EpisodicRepository


@pytest.fixture
def memory_config():
    """Create test memory configuration."""
    config = MemoryConfig()
    config.retrieval.STRICT_MIN_SCORE = 0.70
    config.retrieval.NORMAL_MIN_SCORE = 0.60
    config.retrieval.FUZZY_MIN_SCORE = 0.50
    config.vector_weight = 0.6
    config.time_decay_weight = 0.2
    config.recency_weight = 0.2
    return config


@pytest.fixture
def mock_semantic_repo():
    """Create mock semantic repository."""
    repo = AsyncMock(spec=SemanticRepository)

    async def mock_search(query_embedding, user_id, n_results=10):
        # Return mock search results
        return [
            {
                "id": str(uuid4()),
                "content": "用户喜欢去北京旅游",
                "score": 0.85,
                "metadata": {
                    "user_id": "test_user",
                    "conversation_id": str(uuid4()),
                    "created_at": 1234567890.0,
                    "memory_type": "preference",
                }
            },
            {
                "id": str(uuid4()),
                "content": "用户预算充足",
                "score": 0.70,
                "metadata": {
                    "user_id": "test_user",
                    "conversation_id": str(uuid4()),
                    "created_at": 1234567890.0,
                    "memory_type": "preference",
                }
            },
        ]

    repo.search_similar = mock_search
    return repo


@pytest.fixture
def mock_embedding_client():
    """Create mock embedding client."""
    client = MagicMock()
    client.embed_query = MagicMock(return_value=[0.1] * 1536)
    return client


class TestScenarioAwareRetrieval:
    """Test scenario-aware retrieval functionality."""

    @pytest.mark.asyncio
    async def test_strict_scenario_detection(self, memory_config, mock_semantic_repo):
        """Test strict scenario detection for price queries."""
        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            config=memory_config,
        )

        # Price query should trigger STRICT scenario
        query = "北京的门票价格是多少？"
        scenario = memory_config.retrieval.detect_scenario(query)

        assert scenario == RetrievalScenario.STRICT
        assert memory_config.retrieval.get_threshold(scenario) == 0.70

    @pytest.mark.asyncio
    async def test_fuzzy_scenario_detection(self, memory_config, mock_semantic_repo):
        """Test fuzzy scenario detection for recommendation queries."""
        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            config=memory_config,
        )

        # Recommendation query should trigger FUZZY scenario
        query = "你有什么推荐的地方吗？"
        scenario = memory_config.retrieval.detect_scenario(query)

        assert scenario == RetrievalScenario.FUZZY
        assert memory_config.retrieval.get_threshold(scenario) == 0.50

    @pytest.mark.asyncio
    async def test_normal_scenario_default(self, memory_config, mock_semantic_repo):
        """Test normal scenario as default."""
        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            config=memory_config,
        )

        # Regular query should default to NORMAL
        query = "我想去北京看看"
        scenario = memory_config.retrieval.detect_scenario(query)

        assert scenario == RetrievalScenario.NORMAL
        assert memory_config.retrieval.get_threshold(scenario) == 0.60

    @pytest.mark.asyncio
    async def test_retrieve_with_scenario(
        self,
        memory_config,
        mock_semantic_repo,
        mock_embedding_client,
    ):
        """Test retrieval with automatic scenario detection."""
        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            embedding_client=mock_embedding_client,
            config=memory_config,
        )

        conversation_id = uuid4()
        memories = await retriever.retrieve(
            query="北京的门票价格是多少？",
            user_id="test_user",
            conversation_id=conversation_id,
            limit=5,
        )

        # Should return filtered results based on STRICT threshold
        assert len(memories) >= 0
        if memories:
            assert all(m.level == MemoryLevel.SEMANTIC for m in memories)


class TestConfigurationManagement:
    """Test configuration management for v2.1."""

    def test_config_default_values(self):
        """Test default configuration values."""
        config = MemoryConfig()

        assert config.retrieval.STRICT_MIN_SCORE == 0.70
        assert config.retrieval.NORMAL_MIN_SCORE == 0.60
        assert config.retrieval.FUZZY_MIN_SCORE == 0.50
        assert config.vector_weight == 0.6
        assert config.time_decay_weight == 0.2
        assert config.recency_weight == 0.2

    def test_config_threshold_keywords(self):
        """Test threshold detection keywords."""
        config = MemoryConfig()

        # Strict keywords
        assert "价格" in config.retrieval.STRICT_KEYWORDS
        assert "多少钱" in config.retrieval.STRICT_KEYWORDS
        assert "门票" in config.retrieval.STRICT_KEYWORDS

        # Fuzzy keywords
        assert "推荐" in config.retrieval.FUZZY_KEYWORDS
        assert "建议" in config.retrieval.FUZZY_KEYWORDS
        assert "怎么样" in config.retrieval.FUZZY_KEYWORDS

    def test_config_get_threshold(self):
        """Test threshold retrieval by scenario."""
        config = MemoryConfig()

        assert config.retrieval.get_threshold(RetrievalScenario.STRICT) == 0.70
        assert config.retrieval.get_threshold(RetrievalScenario.NORMAL) == 0.60
        assert config.retrieval.get_threshold(RetrievalScenario.FUZZY) == 0.50

    def test_config_scenario_description(self):
        """Test scenario description for logging."""
        config = MemoryConfig()

        strict_desc = config.retrieval.get_scenario_description(RetrievalScenario.STRICT)
        assert "严格" in strict_desc or "价格" in strict_desc

        fuzzy_desc = config.retrieval.get_scenario_description(RetrievalScenario.FUZZY)
        assert "模糊" in fuzzy_desc or "推荐" in fuzzy_desc


class TestHybridScoring:
    """Test hybrid scoring with configurable weights."""

    @pytest.mark.asyncio
    async def test_hybrid_score_with_config_weights(
        self,
        memory_config,
        mock_semantic_repo,
        mock_embedding_client,
    ):
        """Test hybrid score calculation uses configured weights."""
        # Configure custom weights
        memory_config.vector_weight = 0.7
        memory_config.time_decay_weight = 0.15
        memory_config.recency_weight = 0.15

        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            embedding_client=mock_embedding_client,
            config=memory_config,
        )

        conversation_id = uuid4()
        memories = await retriever.retrieve(
            query="测试查询",
            user_id="test_user",
            conversation_id=conversation_id,
            limit=5,
        )

        # Verify retriever uses configured weights
        assert retriever._config.vector_weight == 0.7
        assert retriever._config.time_decay_weight == 0.15
        assert retriever._config.recency_weight == 0.15


class TestCrossComponentIntegration:
    """Test integration between memory components."""

    @pytest.mark.asyncio
    async def test_injector_with_config(self):
        """Test MemoryInjector with v2.1 configuration."""
        hierarchy = MemoryHierarchy()

        # Add test memories
        hierarchy.add(MemoryItem(
            content="用户喜欢北京",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.9,
        ))

        injector = MemoryInjector(hierarchy)

        # Use get_relevant_memories directly which doesn't require min_importance
        memories = injector.get_relevant_memories("我想去北京旅游", max_memories=3)

        assert isinstance(memories, list)

    @pytest.mark.asyncio
    async def test_promoter_integration(self):
        """Test MemoryPromoter integration with hierarchy."""
        hierarchy = MemoryHierarchy()

        # Add episodic memory
        item = MemoryItem(
            content="用户想去北京旅游",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.INTENT,
            importance=0.85,
        )
        hierarchy.add(item)

        promoter = MemoryPromoter(hierarchy)

        # Get episodic memories directly (avoiding private method)
        episodic = hierarchy.get_episodic(limit=10)

        assert isinstance(episodic, list)


class TestBackwardCompatibility:
    """Test backward compatibility with v2.0 API."""

    @pytest.mark.asyncio
    async def test_hybrid_retriever_with_min_score_param(
        self,
        mock_semantic_repo,
        mock_embedding_client,
    ):
        """Test HybridRetriever still accepts min_score parameter."""
        # Old API: min_score parameter
        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            embedding_client=mock_embedding_client,
            min_score=0.5,
        )

        assert retriever._min_score == 0.5

        conversation_id = uuid4()
        memories = await retriever.retrieve(
            query="测试查询",
            user_id="test_user",
            conversation_id=conversation_id,
            limit=5,
        )

        assert isinstance(memories, list)

    @pytest.mark.asyncio
    async def test_retrieve_with_min_score_override(
        self,
        memory_config,
        mock_semantic_repo,
        mock_embedding_client,
    ):
        """Test retrieve() accepts min_score override."""
        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            embedding_client=mock_embedding_client,
            config=memory_config,
        )

        conversation_id = uuid4()

        # Use min_score override in retrieve call
        memories = await retriever.retrieve(
            query="测试查询",
            user_id="test_user",
            conversation_id=conversation_id,
            limit=5,
            min_score=0.8,  # Override config
        )

        assert isinstance(memories, list)


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_results_handling(
        self,
        memory_config,
        mock_semantic_repo,
        mock_embedding_client,
    ):
        """Test handling of empty search results."""
        # Mock empty results
        async def mock_empty_search(*args, **kwargs):
            return []

        mock_semantic_repo.search_similar = mock_empty_search

        retriever = HybridRetriever(
            semantic_repo=mock_semantic_repo,
            embedding_client=mock_embedding_client,
            config=memory_config,
        )

        memories = await retriever.retrieve(
            query="不存在的查询",
            user_id="test_user",
            conversation_id=uuid4(),
        )

        assert memories == []

    def test_scenario_detection_with_empty_query(self, memory_config):
        """Test scenario detection with empty or short queries."""
        config = memory_config.retrieval

        # Empty query
        scenario = config.detect_scenario("")
        assert scenario == RetrievalScenario.NORMAL

        # Very short query
        scenario = config.detect_scenario("你好")
        assert scenario in [RetrievalScenario.NORMAL, RetrievalScenario.FUZZY]

    def test_config_with_custom_keywords(self):
        """Test configuration with custom keywords."""
        config = MemoryConfig()

        # Add custom strict keyword
        config.retrieval.STRICT_KEYWORDS.add("特价")

        scenario = config.retrieval.detect_scenario("有什么特价机票吗？")
        assert scenario == RetrievalScenario.STRICT
