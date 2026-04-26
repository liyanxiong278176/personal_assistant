"""Comprehensive intent classification evaluation on 1000 test cases.

Evaluates:
1. Overall accuracy and per-intent F1 scores
2. LLM call reduction rate (cache + rule hit rate)
3. High-frequency coverage (Pareto principle)
4. Strategy distribution (cache/rule/llm/fallback)
5. Confusion matrix and error analysis

Usage:
    cd backend
    python -m eval.run_evaluation [--cases eval/test_cases.json] [--limit 100]
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Metrics
# ============================================================================

class EvalMetrics:
    """Collect and compute evaluation metrics."""

    def __init__(self):
        self.results: list[dict] = []
        self.intent_stats: dict[str, dict] = defaultdict(
            lambda: {"tp": 0, "fp": 0, "fn": 0, "total": 0, "correct": 0}
        )
        self.category_stats: dict[str, dict] = defaultdict(
            lambda: {"correct": 0, "total": 0}
        )
        self.strategy_counts: Counter = Counter()
        self.confidence_by_strategy: dict[str, list[float]] = defaultdict(list)
        self.latency_by_strategy: dict[str, list[float]] = defaultdict(list)
        self.errors: list[dict] = []

    def record(
        self,
        case_id: int,
        query: str,
        expected_intent: str,
        predicted_intent: str,
        strategy: str,
        confidence: float,
        latency_ms: float,
        category: str,
    ):
        is_correct = expected_intent == predicted_intent

        self.results.append({
            "case_id": case_id,
            "query": query,
            "expected": expected_intent,
            "predicted": predicted_intent,
            "strategy": strategy,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "category": category,
            "correct": is_correct,
        })

        # Intent-level stats
        self.intent_stats[expected_intent]["total"] += 1
        if is_correct:
            self.intent_stats[expected_intent]["correct"] += 1
            self.intent_stats[expected_intent]["tp"] += 1
        else:
            self.intent_stats[expected_intent]["fn"] += 1
            self.intent_stats[predicted_intent]["fp"] += 1
            self.errors.append({
                "case_id": case_id,
                "query": query,
                "expected": expected_intent,
                "predicted": predicted_intent,
                "strategy": strategy,
                "confidence": confidence,
                "category": category,
            })

        # Category stats
        self.category_stats[category]["total"] += 1
        if is_correct:
            self.category_stats[category]["correct"] += 1

        # Strategy stats
        self.strategy_counts[strategy] += 1
        self.confidence_by_strategy[strategy].append(confidence)
        self.latency_by_strategy[strategy].append(latency_ms)

    def compute_f1(self, intent: str) -> dict:
        stats = self.intent_stats[intent]
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        return {"precision": precision, "recall": recall, "f1": f1}

    def compute_llm_reduction(self) -> dict:
        """Compute how many LLM calls were saved.

        LLM reduction = cases handled by cache or rule strategy (no LLM needed).
        """
        total = len(self.results)
        cache_hits = self.strategy_counts.get("CacheStrategy", 0)
        rule_hits = self.strategy_counts.get("RuleStrategy", 0)
        no_llm = cache_hits + rule_hits
        llm_calls = total - no_llm

        return {
            "total_queries": total,
            "cache_hits": cache_hits,
            "rule_hits": rule_hits,
            "llm_calls": llm_calls,
            "no_llm_total": no_llm,
            "llm_reduction_pct": round(no_llm / total * 100, 1) if total > 0 else 0,
        }

    def compute_confusion_matrix(self) -> dict:
        """Build confusion matrix: matrix[expected][predicted] = count."""
        matrix = defaultdict(lambda: defaultdict(int))
        for r in self.results:
            matrix[r["expected"]][r["predicted"]] += 1
        return dict(matrix)

    def compute_high_freq_coverage(self) -> dict:
        """Compute high-frequency query coverage metrics.

        "80% high-frequency coverage" means:
        - Among high_freq category test cases, what percentage are correctly classified
        - AND what percentage are handled without LLM (rule/cache)
        """
        high_freq_results = [r for r in self.results if r["category"] == "high_freq"]
        if not high_freq_results:
            return {"coverage": 0, "accuracy": 0, "no_llm_rate": 0}

        correct = sum(1 for r in high_freq_results if r["correct"])
        no_llm = sum(
            1 for r in high_freq_results
            if r["strategy"] in ("CacheStrategy", "RuleStrategy")
        )

        return {
            "total_high_freq": len(high_freq_results),
            "correct": correct,
            "accuracy": round(correct / len(high_freq_results) * 100, 1),
            "no_llm": no_llm,
            "no_llm_rate": round(no_llm / len(high_freq_results) * 100, 1),
        }

    def generate_report(self) -> str:
        """Generate formatted evaluation report."""
        lines = []
        total = len(self.results)
        correct = sum(1 for r in self.results if r["correct"])
        accuracy = correct / total * 100 if total > 0 else 0

        lines.append("")
        lines.append("=" * 70)
        lines.append("         意图分类完整评估报告 (1000条仿真数据)")
        lines.append("=" * 70)

        # --- Overall ---
        lines.append(f"\n【总体指标】")
        lines.append(f"  测试用例: {total} 条")
        lines.append(f"  正确分类: {correct} 条")
        lines.append(f"  整体准确率: {accuracy:.1f}%")

        # --- Per-intent F1 ---
        lines.append(f"\n【各意图 F1 分数】")
        lines.append(f"  {'意图':12s} {'数量':>5s} {'准确率':>7s} {'精确率':>7s} {'召回率':>7s} {'F1':>7s}")
        lines.append("  " + "-" * 50)
        for intent in sorted(self.intent_stats.keys()):
            stats = self.intent_stats[intent]
            f1 = self.compute_f1(intent)
            acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
            lines.append(
                f"  {intent:12s} {stats['total']:5d} "
                f"{acc:6.1f}% "
                f"{f1['precision']:6.1%} "
                f"{f1['recall']:6.1%} "
                f"{f1['f1']:6.1%}"
            )

        # --- Category breakdown ---
        lines.append(f"\n【频率分层准确率】")
        lines.append(f"  {'层级':12s} {'数量':>5s} {'正确':>5s} {'准确率':>7s}")
        lines.append("  " + "-" * 35)
        for cat in ["high_freq", "mid_freq", "low_freq"]:
            stats = self.category_stats[cat]
            acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
            lines.append(f"  {cat:12s} {stats['total']:5d} {stats['correct']:5d} {acc:6.1f}%")

        # --- Strategy distribution ---
        lines.append(f"\n【策略分布】")
        lines.append(f"  {'策略':20s} {'数量':>5s} {'占比':>7s} {'平均置信度':>10s} {'平均延迟':>10s}")
        lines.append("  " + "-" * 55)
        for strategy, count in self.strategy_counts.most_common():
            pct = count / total * 100
            avg_conf = sum(self.confidence_by_strategy[strategy]) / count
            avg_lat = sum(self.latency_by_strategy[strategy]) / count
            lines.append(
                f"  {strategy:20s} {count:5d} {pct:6.1f}% {avg_conf:9.2f} {avg_lat:8.1f}ms"
            )

        # --- LLM reduction ---
        llm = self.compute_llm_reduction()
        lines.append(f"\n【LLM调用减少分析】")
        lines.append(f"  总查询数:       {llm['total_queries']}")
        lines.append(f"  缓存命中:       {llm['cache_hits']} ({llm['cache_hits']/total*100:.1f}%)")
        lines.append(f"  规则命中:       {llm['rule_hits']} ({llm['rule_hits']/total*100:.1f}%)")
        lines.append(f"  LLM调用:       {llm['llm_calls']} ({llm['llm_calls']/total*100:.1f}%)")
        lines.append(f"  LLM减少率:     {llm['llm_reduction_pct']}%")

        # Estimate cost savings
        # DeepSeek: ~0.001元/次 for intent classification (~300 tokens)
        cost_per_llm_call = 0.001  # CNY
        baseline_cost = total * cost_per_llm_call
        actual_cost = llm["llm_calls"] * cost_per_llm_call
        lines.append(f"\n  成本估算 (DeepSeek):")
        lines.append(f"    全LLM基线:    ¥{baseline_cost:.3f}")
        lines.append(f"    实际成本:     ¥{actual_cost:.3f}")
        lines.append(f"    节省:        ¥{baseline_cost - actual_cost:.3f} ({llm['llm_reduction_pct']}%)")

        # --- High frequency coverage ---
        hf = self.compute_high_freq_coverage()
        lines.append(f"\n【高频查询覆盖 (帕累托原则)】")
        lines.append(f"  高频查询数:     {hf['total_high_freq']}")
        lines.append(f"  正确分类:       {hf['correct']} ({hf['accuracy']}%)")
        lines.append(f"  无LLM命中:      {hf['no_llm']} ({hf['no_llm_rate']}%)")
        lines.append(f"  \"80%覆盖\"达成: {'✅' if hf['accuracy'] >= 80 else '❌'} (准确率 {hf['accuracy']}% >= 80%)")

        # --- Confusion matrix (top errors) ---
        lines.append(f"\n【混淆矩阵 - 前10错误模式】")
        matrix = self.compute_confusion_matrix()
        error_pairs = []
        for expected, predicted_map in matrix.items():
            for predicted, count in predicted_map.items():
                if expected != predicted:
                    error_pairs.append((expected, predicted, count))
        error_pairs.sort(key=lambda x: -x[2])

        lines.append(f"  {'期望':12s} -> {'实际':12s} {'次数':>5s}")
        lines.append("  " + "-" * 35)
        for expected, predicted, count in error_pairs[:10]:
            lines.append(f"  {expected:12s} -> {predicted:12s} {count:5d}")

        # --- Resume metrics (面试展示) ---
        lines.append(f"\n{'='*70}")
        lines.append(f"【简历/面试指标总结】")
        lines.append(f"  意图分类准确率:      {accuracy:.1f}% (基于{total}条仿真测试)")
        lines.append(f"  高频查询覆盖:        {hf['accuracy']}%")
        lines.append(f"  LLM调用减少:         {llm['llm_reduction_pct']}%")
        lines.append(f"  平均响应时间:")
        for strategy in ["CacheStrategy", "RuleStrategy", "LLMStrategy"]:
            if strategy in self.latency_by_strategy:
                lats = self.latency_by_strategy[strategy]
                avg = sum(lats) / len(lats)
                lines.append(f"    {strategy}: {avg:.1f}ms")
        lines.append(f"{'='*70}")
        lines.append("")

        return "\n".join(lines)


# ============================================================================
# Evaluation runner
# ============================================================================

async def run_evaluation(
    cases_path: str = "eval/test_cases.json",
    limit: Optional[int] = None,
    use_llm: bool = True,
) -> EvalMetrics:
    """Run evaluation on test cases.

    Args:
        cases_path: Path to test cases JSON
        limit: Max cases to evaluate (None = all)
        use_llm: Whether to enable LLM strategy

    Returns:
        EvalMetrics with all results
    """
    # Load test cases
    with open(cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    if limit:
        cases = cases[:limit]

    print(f"\n加载 {len(cases)} 条测试用例...")

    # Build router
    from app.core.intent import IntentRouter, RuleStrategy
    from app.core.intent.strategies import LLMStrategy
    from app.core.intent.strategies.cache import CacheStrategy, ClassificationCache
    from app.core.intent.strategies.semantic_validator import SemanticValidator
    from app.core.intent.config import IntentRouterConfig
    from app.core.llm import LLMClient
    from app.core.context import RequestContext

    strategies = []
    semantic_validator = None
    llm_client = None

    # L1 cache
    classification_cache = ClassificationCache(max_size=1000)
    strategies.append(CacheStrategy(cache=classification_cache))

    # Rule strategy
    strategies.append(RuleStrategy(max_confidence=0.85))

    # LLM strategy + semantic validator (optional)
    if use_llm:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            llm_client = LLMClient(api_key=api_key)
            strategies.append(LLMStrategy(llm_client=llm_client))
            # Enable semantic validator for high-confidence rule results with exclusion keywords
            semantic_validator = SemanticValidator(llm_client=llm_client)
        else:
            print("WARNING: DEEPSEEK_API_KEY not set, LLM strategy disabled")

    # Raise Rule return threshold: mid_confidence 0.5→0.7
    # Rule results with 0.5-0.7 confidence now fall through to LLM
    config = IntentRouterConfig(mid_confidence=0.7)

    router = IntentRouter(
        strategies=strategies,
        config=config,
        semantic_validator=semantic_validator,
    )

    metrics = EvalMetrics()

    print(f"开始评估...")
    for i, case in enumerate(cases):
        if (i + 1) % 100 == 0:
            print(f"  进度: {i+1}/{len(cases)}...")

        start = time.perf_counter()
        ctx = RequestContext(message=case["query"])
        result = await router.classify(ctx)
        latency_ms = (time.perf_counter() - start) * 1000

        metrics.record(
            case_id=case["id"],
            query=case["query"],
            expected_intent=case["expected_intent"],
            predicted_intent=result.intent,
            strategy=result.strategy or result.method or "unknown",
            confidence=result.confidence,
            latency_ms=latency_ms,
            category=case["category"],
        )

    # Print report
    report = metrics.generate_report()
    print(report)

    # Save detailed results
    output_path = Path(cases_path).parent / "eval_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": len(cases),
                "correct": sum(1 for r in metrics.results if r["correct"]),
                "accuracy": sum(1 for r in metrics.results if r["correct"]) / len(cases),
                "llm_reduction": metrics.compute_llm_reduction(),
                "high_freq_coverage": metrics.compute_high_freq_coverage(),
            },
            "errors": metrics.errors,
            "strategy_distribution": dict(metrics.strategy_counts),
            "confusion_matrix": {k: dict(v) for k, v in metrics.compute_confusion_matrix().items()},
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_path}")

    return metrics


def main():
    import io
    # Fix Windows console encoding
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description="Run intent evaluation")
    parser.add_argument("--cases", type=str, default="eval/test_cases.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM strategy")
    args = parser.parse_args()

    asyncio.run(run_evaluation(
        cases_path=args.cases,
        limit=args.limit,
        use_llm=not args.no_llm,
    ))


if __name__ == "__main__":
    main()
