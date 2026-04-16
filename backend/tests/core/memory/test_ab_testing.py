"""Tests for A/B Testing Framework."""

import asyncio
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from app.core.memory.ab_testing import (
    MemoryExperiment,
    ParameterVariant,
    QueryResult,
    VariantMetrics,
    ExperimentResult,
    BASELINE_VARIANT,
    HIGH_SEMANTIC_VARIANT,
    BALANCED_VARIANT,
    run_quick_experiment,
)


class TestParameterVariant:
    """Test ParameterVariant dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        variant = ParameterVariant(
            name="test",
            description="Test variant",
            vector_weight=0.5,
        )

        data = variant.to_dict()

        assert data["name"] == "test"
        assert data["vector_weight"] == 0.5

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "name": "test",
            "description": "Test variant",
            "vector_weight": 0.5,
            "time_decay_weight": 0.2,
            "recency_weight": 0.2,
            "strict_threshold": 0.7,
            "normal_threshold": 0.6,
            "fuzzy_threshold": 0.5,
            "promotion_threshold": 0.7,
            "discard_threshold": 0.4,
            "forgetting_threshold": 0.3,
            "decay_halflife": 30,
        }

        variant = ParameterVariant.from_dict(data)

        assert variant.name == "test"
        assert variant.vector_weight == 0.5


class TestQueryResult:
    """Test QueryResult dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = QueryResult(
            variant_name="baseline",
            query="测试查询",
            scenario="strict",
            retrieved_count=5,
            retrieval_time_ms=150.5,
            top_score=0.85,
            top_relevance="high",
        )

        data = result.to_dict()

        assert data["variant_name"] == "baseline"
        assert data["retrieved_count"] == 5
        assert data["top_score"] == 0.85


class TestVariantMetrics:
    """Test VariantMetrics aggregation."""

    def test_add_result(self):
        """Test adding query results to metrics."""
        metrics = VariantMetrics(variant_name="baseline")

        # Add successful retrieval
        result1 = QueryResult(
            variant_name="baseline",
            query="测试查询1",
            scenario="normal",
            retrieved_count=5,
            retrieval_time_ms=100.0,
            top_score=0.8,
            top_relevance="high",
            user_feedback=True,
        )
        metrics.add_result(result1)

        assert metrics.total_queries == 1
        assert metrics.successful_retrievals == 1
        assert metrics.avg_retrieved_count == 5.0
        assert metrics.avg_top_score == 0.8

        # Add failed retrieval
        result2 = QueryResult(
            variant_name="baseline",
            query="测试查询2",
            scenario="fuzzy",
            retrieved_count=0,
            retrieval_time_ms=50.0,
            top_score=0.0,
            top_relevance="low",
        )
        metrics.add_result(result2)

        assert metrics.total_queries == 2
        assert metrics.failed_retrievals == 1
        assert metrics.avg_retrieved_count == 2.5  # (5 + 0) / 2

    def test_user_satisfaction_calculation(self):
        """Test user satisfaction rate calculation."""
        metrics = VariantMetrics(variant_name="baseline")

        # Add results with feedback
        metrics.add_result(QueryResult(
            variant_name="baseline",
            query="测试1",
            scenario="normal",
            retrieved_count=3,
            retrieval_time_ms=100.0,
            top_score=0.7,
            top_relevance="medium",
            user_feedback=True,
        ))
        metrics.add_result(QueryResult(
            variant_name="baseline",
            query="测试2",
            scenario="strict",
            retrieved_count=2,
            retrieval_time_ms=80.0,
            top_score=0.6,
            top_relevance="medium",
            user_feedback=False,
        ))
        metrics.add_result(QueryResult(
            variant_name="baseline",
            query="测试3",
            scenario="fuzzy",
            retrieved_count=4,
            retrieval_time_ms=90.0,
            top_score=0.75,
            top_relevance="medium",
            user_feedback=True,
        ))

        # 2 out of 3 positive = 0.667
        assert abs(metrics.user_satisfaction_rate - 0.667) < 0.01


class TestExperimentResult:
    """Test ExperimentResult dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = ExperimentResult(
            experiment_name="test_exp",
            timestamp=datetime.utcnow().isoformat(),
            total_queries=10,
            variant_metrics={
                "baseline": VariantMetrics(variant_name="baseline"),
                "variant_a": VariantMetrics(variant_name="variant_a"),
            },
            winning_variant="baseline",
            winning_reason="Best performance",
        )

        data = result.to_dict()

        assert data["experiment_name"] == "test_exp"
        assert data["total_queries"] == 10
        assert data["winning_variant"] == "baseline"


class TestMemoryExperiment:
    """Test MemoryExperiment class."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test experiment initialization."""
        test_queries = [
            {"query": "测试查询1", "scenario": "strict"},
            {"query": "测试查询2", "scenario": "normal"},
        ]

        experiment = MemoryExperiment(
            name="test_init",
            variants=[BASELINE_VARIANT],
            test_queries=test_queries,
            semantic_repo=AsyncMock(),
            embedding_client=AsyncMock(),
        )

        assert experiment.name == "test_init"
        assert len(experiment.variants) == 1
        assert experiment._output_dir == "./data/experiments"

    @pytest.mark.asyncio
    async def test_simulate_retrieval(self):
        """Test retrieval simulation."""
        experiment = MemoryExperiment(
            name="test_simulate",
            variants=[BASELINE_VARIANT],
            test_queries=[],
        )

        retrieved_count, top_score = await experiment._simulate_retrieval(
            variant=BASELINE_VARIANT,
            query="北京的故宫门票价格是多少？",
            scenario="strict",
        )

        assert retrieved_count >= 0
        assert 0 <= top_score <= 1.0

    @pytest.mark.asyncio
    async def test_analyze_winner(self):
        """Test winner analysis logic."""
        # Create mock metrics
        metrics = {
            "baseline": VariantMetrics(variant_name="baseline"),
            "variant_a": VariantMetrics(variant_name="variant_a"),
        }

        # Add some results
        metrics["baseline"].total_queries = 10
        metrics["baseline"].successful_retrievals = 8
        metrics["baseline"].avg_retrieval_time_ms = 50.0

        metrics["variant_a"].total_queries = 10
        metrics["variant_a"].successful_retrievals = 9
        metrics["variant_a"].avg_retrieval_time_ms = 45.0

        experiment = MemoryExperiment("", [], None, None)

        winner, reason = experiment._analyze_winner(metrics)

        # variant_a has better recall and speed
        assert winner == "variant_a"


class TestQuickExperiment:
    """Test convenience function for quick experiments."""

    @pytest.mark.asyncio
    async def test_run_quick_experiment(self):
        """Test quick experiment convenience function."""
        queries = [
            "北京的门票价格是多少？",
            "你有什么推荐？",
            "我想去旅游",
        ]

        result = await run_quick_experiment(queries, variants=[
            BASELINE_VARIANT,
            BALANCED_VARIANT,
        ])

        assert result.total_queries == 3
        assert result.winning_variant is not None


class TestPredefinedVariants:
    """Test predefined parameter variants."""

    def test_baseline_variant(self):
        """Test baseline variant has expected values."""
        assert BASELINE_VARIANT.vector_weight == 0.6
        assert BASELINE_VARIANT.strict_threshold == 0.70
        assert BASELINE_VARIANT.decay_halflife == 30

    def test_high_semantic_variant(self):
        """Test high semantic variant prioritizes semantic similarity."""
        assert HIGH_SEMANTIC_VARIANT.vector_weight == 0.7
        assert HIGH_SEMANTIC_VARIANT.time_decay_weight == 0.15
        assert HIGH_SEMANTIC_VARIANT.recency_weight == 0.15

    def test_aggressive_variant(self):
        """Test aggressive variant has lower thresholds."""
        assert AGGRESSIVE_VARIANT.strict_threshold == 0.65  # Lower
        assert AGGRESSIVE_VARIANT.fuzzy_threshold == 0.45   # Lower
        assert AGGRESSIVE_VARIANT.promotion_threshold == 0.65  # Lower
        assert AGGRESSIVE_VARIANT.forgetting_threshold == 0.25  # Lower
