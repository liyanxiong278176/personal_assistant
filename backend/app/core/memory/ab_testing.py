"""A/B Testing Framework for Memory Management Parameters.

This module provides tools to experiment with different parameter configurations
for the memory management system, including:
- Hybrid scoring weights (vector, time_decay, recency)
- Scenario thresholds (strict, normal, fuzzy)
- Promotion thresholds
- Forgetting curve parameters

Usage:
    ```python
    from app.core.memory.ab_testing import (
        MemoryExperiment,
        ExperimentConfig,
        ExperimentResult,
        ParameterVariant,
    )

    # Define parameter variants to test
    variants = [
        ParameterVariant(
            name="baseline",
            vector_weight=0.6,
            time_decay_weight=0.2,
            recency_weight=0.2,
            strict_threshold=0.7,
        ),
        ParameterVariant(
            name="higher_semantic",
            vector_weight=0.7,
            time_decay_weight=0.15,
            recency_weight=0.15,
            strict_threshold=0.75,
        ),
    ]

    # Run experiment
    experiment = MemoryExperiment(
        name="hybrid_weights_v1",
        variants=variants,
        test_queries=test_queries,
    )

    results = await experiment.run()
    experiment.generate_report()
    ```
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


class ParameterType(str, Enum):
    """Types of parameters that can be tested."""
    VECTOR_WEIGHT = "vector_weight"
    TIME_DECAY_WEIGHT = "time_decay_weight"
    RECENCY_WEIGHT = "recency_weight"
    STRICT_THRESHOLD = "strict_threshold"
    NORMAL_THRESHOLD = "normal_threshold"
    FUZZY_THRESHOLD = "fuzzy_threshold"
    PROMOTION_THRESHOLD = "promotion_threshold"
    DISCARD_THRESHOLD = "discard_threshold"
    FORGETTING_THRESHOLD = "forgetting_threshold"
    DECAY_HALFLIFE = "decay_halflife"


@dataclass
class ParameterVariant:
    """A single variant of parameter configuration."""

    name: str
    description: str

    # Hybrid scoring weights
    vector_weight: float = 0.6
    time_decay_weight: float = 0.2
    recency_weight: float = 0.2

    # Scenario thresholds
    strict_threshold: float = 0.70
    normal_threshold: float = 0.60
    fuzzy_threshold: float = 0.50

    # Promotion thresholds
    promotion_threshold: float = 0.7
    discard_threshold: float = 0.4

    # Forgetting curve
    forgetting_threshold: float = 0.3
    decay_halflife: int = 30

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "vector_weight": self.vector_weight,
            "time_decay_weight": self.time_decay_weight,
            "recency_weight": self.recency_weight,
            "strict_threshold": self.strict_threshold,
            "normal_threshold": self.normal_threshold,
            "fuzzy_threshold": self.fuzzy_threshold,
            "promotion_threshold": self.promotion_threshold,
            "discard_threshold": self.discard_threshold,
            "forgetting_threshold": self.forgetting_threshold,
            "decay_halflife": self.decay_halflife,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParameterVariant":
        """Create from dictionary."""
        return cls(**data)


# Predefined variant configurations
BASELINE_VARIANT = ParameterVariant(
    name="baseline",
    description="Current production configuration",
    vector_weight=0.6,
    time_decay_weight=0.2,
    recency_weight=0.2,
    strict_threshold=0.70,
    normal_threshold=0.60,
    fuzzy_threshold=0.50,
    promotion_threshold=0.7,
    discard_threshold=0.4,
    forgetting_threshold=0.3,
    decay_halflife=30,
)

HIGH_SEMANTIC_VARIANT = ParameterVariant(
    name="high_semantic",
    description="Higher weight on semantic similarity",
    vector_weight=0.7,
    time_decay_weight=0.15,
    recency_weight=0.15,
    strict_threshold=0.75,
    normal_threshold=0.65,
    fuzzy_threshold=0.55,
    promotion_threshold=0.75,
    discard_threshold=0.45,
    forgetting_threshold=0.35,
    decay_halflife=30,
)

HIGH_RECENCY_VARIANT = ParameterVariant(
    name="high_recency",
    description="Higher weight on conversation recency",
    vector_weight=0.5,
    time_decay_weight=0.2,
    recency_weight=0.3,
    strict_threshold=0.70,
    normal_threshold=0.60,
    fuzzy_threshold=0.50,
    promotion_threshold=0.7,
    discard_threshold=0.4,
    forgetting_threshold=0.3,
    decay_halflife=30,
)

BALANCED_VARIANT = ParameterVariant(
    name="balanced",
    description="Balanced approach with equal weights",
    vector_weight=0.5,
    time_decay_weight=0.25,
    recency_weight=0.25,
    strict_threshold=0.70,
    normal_threshold=0.60,
    fuzzy_threshold=0.50,
    promotion_threshold=0.7,
    discard_threshold=0.4,
    forgetting_threshold=0.3,
    decay_halflife=30,
)

AGGRESSIVE_VARIANT = ParameterVariant(
    name="aggressive",
    description="Lower thresholds for more recall",
    vector_weight=0.6,
    time_decay_weight=0.2,
    recency_weight=0.2,
    strict_threshold=0.65,  # Lower
    normal_threshold=0.55,  # Lower
    fuzzy_threshold=0.45,  # Lower
    promotion_threshold=0.65,  # Lower
    discard_threshold=0.3,  # Lower
    forgetting_threshold=0.25,  # Lower
    decay_halflife=30,
)


@dataclass
class QueryResult:
    """Result of a single query in an experiment."""

    variant_name: str
    query: str
    scenario: str

    # Retrieval metrics
    retrieved_count: int
    retrieval_time_ms: float

    # Top result metrics
    top_score: float
    top_relevance: str  # "high", "medium", "low"

    # User feedback (if available)
    user_feedback: Optional[bool] = None

    # Memory details
    retrieved_memories: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variant_name": self.variant_name,
            "query": self.query,
            "scenario": self.scenario,
            "retrieved_count": self.retrieved_count,
            "retrieval_time_ms": self.retrieval_time_ms,
            "top_score": self.top_score,
            "top_relevance": self.top_relevance,
            "user_feedback": self.user_feedback,
        }


@dataclass
class VariantMetrics:
    """Aggregated metrics for a single variant."""

    variant_name: str
    total_queries: int = 0
    successful_retrievals: int = 0
    failed_retrievals: int = 0
    avg_retrieved_count: float = 0.0
    avg_retrieval_time_ms: float = 0.0
    avg_top_score: float = 0.0
    user_satisfaction_rate: float = 0.0

    def add_result(self, result: QueryResult) -> None:
        """Add a query result to metrics."""
        self.total_queries += 1

        if result.retrieved_count > 0:
            self.successful_retrievals += 1
            self.avg_retrieved_count = (
                (self.avg_retrieved_count * (self.successful_retrievals - 1) +
                 result.retrieved_count
            ) / self.successful_retrievals
            )
            self.avg_top_score = (
                (self.avg_top_score * (self.successful_retrievals - 1) +
                 result.top_score
            ) / self.successful_retrievals
            )
        else:
            self.failed_retrievals += 1

        self.avg_retrieval_time_ms = (
            (self.avg_retrieval_time_ms * (self.total_queries - 1) +
             result.retrieval_time_ms)
        ) / self.total_queries

        if result.user_feedback is not None:
            positive_count = sum(
                1 for r in [result]
                if r.user_feedback is True
            )
            total_feedback = sum(
                1 for r in [result]
                if r.user_feedback is not None
            )
            if total_feedback > 0:
                self.user_satisfaction_rate = positive_count / total_feedback

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variant_name": self.variant_name,
            "total_queries": self.total_queries,
            "successful_retrievals": self.successful_retrievals,
            "failed_retrievals": self.failed_retrievals,
            "recall_rate": self.successful_retrievals / self.total_queries if self.total_queries > 0 else 0,
            "avg_retrieved_count": round(self.avg_retrieved_count, 2),
            "avg_retrieval_time_ms": round(self.avg_retrieval_time_ms, 2),
            "avg_top_score": round(self.avg_top_score, 3),
            "user_satisfaction_rate": round(self.user_satisfaction_rate, 3),
        }


@dataclass
class ExperimentResult:
    """Results of an A/B testing experiment."""

    experiment_name: str
    timestamp: str
    total_queries: int

    variant_metrics: Dict[str, VariantMetrics]

    # Winner analysis
    winning_variant: Optional[str] = None
    winning_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "experiment_name": self.experiment_name,
            "timestamp": self.timestamp,
            "total_queries": self.total_queries,
            "variant_metrics": {
                name: metrics.to_dict()
                for name, metrics in self.variant_metrics.items()
            },
            "winning_variant": self.winning_variant,
            "winning_reason": self.winning_reason,
        }


class MemoryExperiment:
    """A/B testing experiment for memory parameters."""

    def __init__(
        self,
        name: str,
        variants: List[ParameterVariant],
        test_queries: List[Dict[str, str]],
        semantic_repo=None,
        embedding_client=None,
        output_dir: Optional[str] = None,
    ):
        """Initialize experiment.

        Args:
            name: Experiment name
            variants: List of parameter variants to test
            test_queries: List of test queries with expected scenarios
            semantic_repo: SemanticRepository for retrieval
            embedding_client: Embedding client for vector generation
            output_dir: Optional directory for result files
        """
        self.name = name
        self.variants = variants
        self.test_queries = test_queries
        self._semantic_repo = semantic_repo
        self._embedding_client = embedding_client
        self._output_dir = output_dir or "./data/experiments"

        # Ensure output directory exists
        Path(self._output_dir).mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[ABTesting] Experiment '{name}' initialized with "
            f"{len(variants)} variants and {len(test_queries)} queries"
        )

    async def run(
        self,
        max_concurrent: int = 5
    ) -> ExperimentResult:
        """Run the A/B testing experiment.

        Args:
            max_concurrent: Maximum concurrent retrievals

        Returns:
            ExperimentResult with all metrics
        """
        logger.info(f"[ABTesting] Running experiment '{self.name}'...")

        variant_metrics = {
            variant.name: VariantMetrics(variant_name=variant.name)
            for variant in self.variants
        }

        all_results: List[QueryResult] = []
        total_queries = 0

        for query_data in self.test_queries:
            query = query_data["query"]
            expected_scenario = query_data.get("scenario", "normal")

            logger.info(
                f"[ABTesting] Testing query: '{query[:50]}...' "
                f"(scenario: {expected_scenario})"
            )

            # Test each variant
            for variant in self.variants:
                result = await self._test_variant(
                    variant,
                    query,
                    expected_scenario
                )
                all_results.append(result)
                variant_metrics[variant.name].add_result(result)

            total_queries += 1

        # Analyze results
        winning_variant, winning_reason = self._analyze_winner(variant_metrics)

        result = ExperimentResult(
            experiment_name=self.name,
            timestamp=datetime.utcnow().isoformat(),
            total_queries=total_queries,
            variant_metrics=variant_metrics,
            winning_variant=winning_variant,
            winning_reason=winning_reason,
        )

        # Save results
        self._save_results(result, all_results)

        logger.info(
            f"[ABTesting] Experiment complete: "
            f"winner={winning_variant}, reason='{winning_reason}'"
        )

        return result

    async def _test_variant(
        self,
        variant: ParameterVariant,
        query: str,
        expected_scenario: str,
    ) -> QueryResult:
        """Test a single variant with a query.

        Args:
            variant: Parameter variant to test
            query: Test query
            expected_scenario: Expected scenario type

        Returns:
            QueryResult with metrics
        """
        start = time.perf_counter()

        try:
            # Simulate retrieval with variant parameters
            # In production, this would use actual HybridRetriever with variant config
            retrieved_count, top_score = await self._simulate_retrieval(
                variant, query, expected_scenario
            )

            retrieval_time = (time.perf_counter() - start) * 1000

            # Determine relevance level
            if top_score >= 0.8:
                top_relevance = "high"
            elif top_score >= 0.6:
                top_relevance = "medium"
            else:
                top_relevance = "low"

            return QueryResult(
                variant_name=variant.name,
                query=query,
                scenario=expected_scenario,
                retrieved_count=retrieved_count,
                retrieval_time_ms=retrieval_time,
                top_score=top_score,
                top_relevance=top_relevance,
            )

        except Exception as e:
            logger.error(f"[ABTesting] Variant {variant.name} failed: {e}")
            return QueryResult(
                variant_name=variant.name,
                query=query,
                scenario=expected_scenario,
                retrieved_count=0,
                retrieval_time_ms=0,
                top_score=0.0,
                top_relevance="error",
            )

    async def _simulate_retrieval(
        self,
        variant: ParameterVariant,
        query: str,
        scenario: str,
    ) -> Tuple[int, float]:
        """Simulate retrieval with variant parameters.

        In production, this would use actual HybridRetriever.
        For now, returns simulated results based on parameter configuration.

        Returns:
            (retrieved_count, top_score)
        """
        # Get threshold for scenario
        if scenario == "strict":
            threshold = variant.strict_threshold
        elif scenario == "normal":
            threshold = variant.normal_threshold
        else:  # fuzzy
            threshold = variant.fuzzy_threshold

        # Simulate vector similarity (would be actual embedding search)
        # Using query length and keyword presence as heuristic
        query_lower = query.lower()

        # Check for keywords that indicate high relevance
        high_relevance_keywords = ["价格", "多少钱", "预算", "喜欢", "推荐", "想去"]
        base_similarity = 0.5

        for keyword in high_relevance_keywords:
            if keyword in query:
                base_similarity = min(base_similarity + 0.3, 0.95)
                break

        # Apply weights to calculate final score
        # Simulate time decay (random but consistent)
        import random
        random.seed(hash(query) % 1000)  # Consistent random

        days_passed = random.randint(1, 60)
        time_decay = pow(0.5, days_passed / variant.decay_halflife)

        # Simulate conversation recency
        recency_score = 1.0 if random.random() > 0.5 else 0.3

        final_score = (
            variant.vector_weight * base_similarity +
            variant.time_decay_weight * time_decay +
            variant.recency_weight * recency_score
        )

        # Determine retrieved count based on score vs threshold
        if final_score >= threshold:
            retrieved_count = random.randint(3, 10)
        else:
            retrieved_count = 0

        return retrieved_count, final_score

    def _analyze_winner(
        self,
        metrics: Dict[str, VariantMetrics]
    ) -> Tuple[Optional[str], str]:
        """Analyze which variant performed best.

        Args:
            metrics: Dictionary of variant metrics

        Returns:
            (winning_variant_name, reason)
        """
        if not metrics:
            return None, "No metrics available"

        # Scoring: prioritize recall + satisfaction + speed
        scores = {}

        for name, metric in metrics.items():
            score = 0.0

            # Recall rate (40% weight) - more results is better
            score += 0.4 * metric.recall_rate

            # User satisfaction (40% weight) - higher is better
            score += 0.4 * metric.user_satisfaction_rate

            # Speed (20% weight) - faster is better
            # Normalize by inverse (assume 100ms is ideal)
            speed_score = max(0, 1 - metric.avg_retrieval_time_ms / 100)
            score += 0.2 * speed_score

            scores[name] = score

        winner = max(scores, key=scores.get)

        # Generate reason
        winner_metrics = metrics[winner]
        reasons = []

        if winner_metrics.recall_rate >= 0.8:
            reasons.append(f"high recall ({winner_metrics.recall_rate:.1%})")
        if winner_metrics.user_satisfaction_rate >= 0.8:
            reasons.append(f"high satisfaction ({winner_metrics.user_satisfaction_rate:.1%})")
        if winner_metrics.avg_retrieval_time_ms <= 50:
            reasons.append(f"fast retrieval ({winner_metrics.avg_retrieval_time_ms:.1f}ms)")

        reason = ", ".join(reasons) if reasons else "balanced performance"

        return winner, reason

    def _save_results(
        self,
        result: ExperimentResult,
        all_results: List[QueryResult],
    ) -> None:
        """Save experiment results to file.

        Args:
            result: Aggregated experiment result
            all_results: All individual query results
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        result_file = Path(self._output_dir) / f"{self.name}_{timestamp}.json"

        import json
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump({
                "result": result.to_dict(),
                "all_results": [r.to_dict() for r in all_results],
                "variants": [v.to_dict() for v in self.variants],
            }, f, ensure_ascii=False, indent=2)

        logger.info(f"[ABTesting] Results saved to {result_file}")

    def generate_report(self) -> str:
        """Generate a human-readable report of the experiment.

        Returns:
            Report text
        """
        # Load latest result
        import json
        import glob

        result_files = sorted(
            Path(self._output_dir).glob(f"{self.name}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not result_files:
            return f"No results found for experiment '{self.name}'"

        with open(result_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        result = ExperimentResult(**data["result"])
        metrics = data["variant_metrics"]

        # Build report
        lines = [
            f"# A/B Testing Report: {self.name}",
            f"Timestamp: {result.timestamp}",
            f"Total Queries: {result.total_queries}",
            "",
            "## Variant Comparison",
            "",
            "| Variant | Queries | Recall | Avg Score | Satisfaction | Speed |",
            "|--------|--------|--------|-----------|--------------|-------|",
        ]

        for name, m in metrics.items():
            lines.append(
                f"| {name} | {m['total_queries']} | {m['recall_rate']:.1%} | "
                f"{m['avg_top_score']:.3f} | {m['user_satisfaction_rate']:.1%} | "
                f"{m['avg_retrieval_time_ms']:.1f}ms |"
            )

        lines.extend([
            "",
            "## Winner",
            "",
            f"**{result.winning_variant}**",
            f"Reason: {result.winning_reason}",
            "",
            "## Recommendations",
            "",
        ])

        if result.winning_variant == "baseline":
            lines.append("✅ Current configuration is optimal, keep using it.")
        elif result.winning_variant == "high_semantic":
            lines.extend([
                "→ Consider increasing semantic weight to 0.7",
                "→ Higher strict threshold (0.75) improves precision.",
            ])
        elif result.winning_variant == "high_recency":
            lines.extend([
                "→ Consider increasing recency weight to 0.3",
                "→ Prioritizes current conversation context.",
            ])
        elif result.winning_variant == "balanced":
            lines.extend([
                "→ Equal weight distribution provides balance.",
                "→ Consider testing with even weights (0.33 each).",
            ])
        elif result.winning_variant == "aggressive":
            lines.extend([
                "→ Lower thresholds improve recall but may reduce precision.",
                "→ Monitor for noise in retrieved results.",
            ])

        report = "\n".join(lines)

        # Save report
        report_file = Path(self._output_dir) / f"{self.name}_report.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info(f"[ABTesting] Report saved to {report_file}")

        return report


# Convenience function for quick experiments
async def run_quick_experiment(
    queries: List[str],
    variants: Optional[List[ParameterVariant]] = None,
) -> ExperimentResult:
    """Run a quick experiment with default variants.

    Args:
        queries: List of test queries
        variants: Optional list of variants (uses defaults if None)

    Returns:
        ExperimentResult
    """
    if variants is None:
        variants = [BASELINE_VARIANT, HIGH_SEMANTIC_VARIANT, BALANCED_VARIANT]

    # Convert simple query list to query data
    query_data = []
    for q in queries:
        if "价格" in q or "多少钱" in q:
            scenario = "strict"
        elif "推荐" in q or "怎么样" in q:
            scenario = "fuzzy"
        else:
            scenario = "normal"

        query_data.append({"query": q, "scenario": scenario})

    experiment = MemoryExperiment(
        name="quick_test",
        variants=variants,
        test_queries=query_data,
    )

    return await experiment.run()


# Example usage
if __name__ == "__main__":
    # Define test queries
    test_queries = [
        {"query": "北京的故宫门票价格是多少？", "scenario": "strict"},
        {"query": "你有什么推荐的景点吗？", "scenario": "fuzzy"},
        {"query": "我想去北京旅游", "scenario": "normal"},
        {"query": "预算5000元够去日本吗？", "scenario": "strict"},
        {"query": "怎么样去上海比较好？", "scenario": "normal"},
    ]

    # Run experiment
    result = asyncio.run(run_quick_experiment(test_queries))

    # Generate report
    experiment = MemoryExperiment("", [], test_queries, None, None)
    report = experiment.generate_report()
    print(report)
