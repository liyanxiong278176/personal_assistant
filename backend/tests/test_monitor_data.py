"""Monitor dashboard test data generation script.

Purpose:
1. Development phase: Generate test data to verify frontend display
2. Demo preparation: Record demo scenario data
3. Stress testing: Verify performance under high data volume
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List

from app.core.intent.router import IntentRouter
from app.core.intent.config import IntentRouterConfig
from app.core.memory.hierarchy import (
    MemoryHierarchy, MemoryItem, MemoryLevel, MemoryType
)
from app.core.context_mgmt.guard import ContextGuard
from app.core.context_mgmt.config import get_default_config
from app.core.context import RequestContext


async def generate_intent_test_data(router: IntentRouter, count: int = 100):
    """Generate intent classification test data.

    Args:
        router: IntentRouter instance
        count: Number of test queries to generate
    """
    test_queries = [
        "北京天气怎么样",
        "推荐一些上海景点",
        "帮我规划三日游",
        "五星级酒店有哪些",
        "素食餐厅推荐",
        "明天去杭州玩什么",
        "预算三千去哪旅游",
        "带孩子去哪里合适",
    ] * 15  # Expand to 100+ queries

    for i, query in enumerate(test_queries[:count]):
        # Record latency manually
        strategy = "CacheStrategy" if hash(query) % 3 == 0 else "RuleStrategy"
        router.record_latency(strategy, 1 + hash(query) % 5)

        # Record classification manually (avoid full classify to prevent field errors)
        router.record_classification(query, strategy, 0.8 + (hash(query) % 20) / 100)

    print(f"Generated {count} intent classification records")


async def generate_memory_test_data(hierarchy: MemoryHierarchy, count: int = 20):
    """Generate memory promotion test data.

    Args:
        hierarchy: MemoryHierarchy instance
        count: Number of test memories to generate
    """
    test_memories = [
        ("用户喜欢素食", MemoryType.PREFERENCE, 0.9),
        ("用户预算充裕", MemoryType.PREFERENCE, 0.85),
        ("用户来自北京", MemoryType.FACT, 0.7),
        ("用户带小孩出行", MemoryType.CONSTRAINT, 0.8),
        ("用户喜欢历史文化", MemoryType.PREFERENCE, 0.88),
        ("用户对海鲜过敏", MemoryType.CONSTRAINT, 0.95),
        ("用户喜欢安静的环境", MemoryType.PREFERENCE, 0.75),
        ("用户计划去上海", MemoryType.INTENT, 0.8),
        ("用户想住五星级酒店", MemoryType.PREFERENCE, 0.85),
        ("用户出行时间在周末", MemoryType.FACT, 0.7),
    ] * 2  # Expand to 20 memories

    for content, mem_type, importance in test_memories[:count]:
        item = MemoryItem(
            content=content,
            level=MemoryLevel.WORKING,
            memory_type=mem_type,
            importance=importance
        )
        hierarchy.promote_to_semantic(item)

    print(f"Generated {count} memory promotion records")


async def generate_context_test_data(guard: ContextGuard):
    """Generate context compression test data.

    Args:
        guard: ContextGuard instance
    """
    # Build long conversation to trigger compression
    messages = [
        {"role": "user", "content": f"测试消息 {i}，这是一段较长的内容用来触发上下文压缩机制。包含更多细节来增加 token 数量。"}
        for i in range(50)
    ]

    await guard.pre_process(messages)
    await guard.post_process(messages)

    print("Generated context compression test data")


async def main():
    """Main test data generation flow."""
    print("=" * 50)
    print("Monitor Dashboard Test Data Generator")
    print("=" * 50)

    # Initialize components
    from app.core.intent.strategies.cache import CacheStrategy
    from app.core.intent.strategies.rule import RuleStrategy
    from app.core.intent.strategies.llm_fallback import LLMFallbackStrategy

    # Create intent router
    strategies = [
        CacheStrategy(),
        RuleStrategy(),
        LLMFallbackStrategy(),
    ]
    router = IntentRouter(strategies=strategies, config=IntentRouterConfig())

    # Create memory hierarchy
    hierarchy = MemoryHierarchy()

    # Create context guard
    guard = ContextGuard(config=get_default_config())

    # Generate test data
    print("\n[1/3] Generating intent classification test data...")
    await generate_intent_test_data(router, count=100)

    print("\n[2/3] Generating memory promotion test data...")
    await generate_memory_test_data(hierarchy, count=20)

    print("\n[3/3] Generating context compression test data...")
    await generate_context_test_data(guard)

    # Export statistics
    stats = {
        "intent": router.get_statistics(),
        "memory": hierarchy.get_context_summary(),
        "context": guard.get_stats(),
        "timestamp": datetime.now().isoformat()
    }

    # Add extended data for monitor dashboard
    stats["intent"]["avg_latency_ms"] = router.avg_latency_ms
    stats["intent"]["recent_classifications"] = router._recent_classifications
    stats["memory"]["promotions"] = hierarchy._promotion_history
    stats["memory"]["semantic_memories"] = [m.to_dict() for m in hierarchy._semantic]

    # Write to file
    output_path = Path("test_monitor_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 50)
    print(f"Test data generated: {output_path.absolute()}")
    print(f"  - Intent classifications: {stats['intent']['total_classifications']}")
    print(f"  - Semantic memories: {stats['memory']['semantic_count']}")
    print(f"  - Compressions triggered: {stats['context']['compression_triggered_count']}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
