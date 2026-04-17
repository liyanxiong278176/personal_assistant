"""
监控面板测试数据生成脚本

用途:
1. 开发阶段：生成测试数据验证前端展示
2. 演示准备：录制演示场景数据
3. 压力测试：验证大数据量下的性能
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.core.intent.router import IntentRouter
from app.core.memory.hierarchy import MemoryHierarchy, MemoryItem, MemoryLevel, MemoryType
from app.core.context_mgmt.guard import ContextGuard
from app.core import QueryEngine
from app.core.llm import LLMClient
from app.core.context import RequestContext


async def generate_intent_test_data(router: IntentRouter, count: int = 100):
    """生成意图识别测试数据"""
    test_queries = [
        "北京天气怎么样",
        "推荐一些上海景点",
        "帮我规划三日游",
        "五星级酒店有哪些",
        "素食餐厅推荐",
        "明天去杭州玩什么",
        "预算三千去哪旅游",
        "带孩子去哪里合适",
    ] * 15  # 扩展到100+条

    for query in test_queries[:count]:
        context = RequestContext(
            message=query,
            conversation_id="test_conv",
            user_id="test_user"
        )
        await router.classify(context)

        # 记录延迟
        router.record_latency("CacheStrategy" if hash(query) % 3 == 0 else "RuleStrategy", 1 + hash(query) % 5)


async def generate_memory_test_data(hierarchy: MemoryHierarchy, count: int = 20):
    """生成记忆晋升测试数据"""
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
    ] * 2  # 扩展到20条

    for content, mem_type, importance in test_memories[:count]:
        item = MemoryItem(
            content=content,
            level=MemoryLevel.WORKING,
            memory_type=mem_type,
            importance=importance
        )
        hierarchy.promote_to_semantic(item)


async def generate_context_test_data(guard: ContextGuard):
    """生成上下文压缩测试数据"""
    # 构造长对话触发压缩
    messages = [{"role": "user", "content": f"测试消息 {i}，这是一段较长的内容用来触发上下文压缩机制。"} for i in range(50)]
    await guard.pre_process(messages)
    await guard.post_process(messages)


async def main():
    """主测试流程"""
    # 初始化组件
    from app.core.intent.config import IntentRouterConfig
    from app.core.intent.strategies.cache import CacheStrategy
    from app.core.intent.strategies.rule import RuleStrategy
    from app.core.intent.strategies.llm_fallback import LLMFallbackStrategy
    from app.core.context_mgmt.config import get_default_config

    # 创建意图路由
    strategies = [
        CacheStrategy(),
        RuleStrategy(),
        LLMFallbackStrategy(),
    ]
    router = IntentRouter(strategies=strategies, config=IntentRouterConfig())

    # 创建记忆层级
    hierarchy = MemoryHierarchy()

    # 创建上下文守卫
    guard = ContextGuard(config=get_default_config())

    # 生成测试数据
    print("生成意图识别测试数据...")
    await generate_intent_test_data(router, count=100)

    print("生成记忆测试数据...")
    await generate_memory_test_data(hierarchy, count=20)

    print("生成上下文压缩测试数据...")
    await generate_context_test_data(guard)

    # 导出统计结果
    stats = {
        "intent": router.get_statistics(),
        "memory": hierarchy.get_context_summary(),
        "context": guard.get_stats(),
        "timestamp": datetime.now().isoformat()
    }

    # 添加扩展数据
    stats["intent"]["avg_latency_ms"] = router.avg_latency_ms
    stats["intent"]["recent_classifications"] = router._recent_classifications
    stats["memory"]["promotions"] = hierarchy._promotion_history
    stats["memory"]["semantic_memories"] = [m.to_dict() for m in hierarchy._semantic]

    output_path = Path("test_monitor_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)

    print(f"测试数据已生成: {output_path.absolute()}")
    print(f"意图分类数: {stats['intent']['total_classifications']}")
    print(f"语义记忆数: {stats['memory']['semantic_count']}")
    print(f"压缩触发次数: {stats['context']['compression_triggered_count']}")


if __name__ == "__main__":
    asyncio.run(main())
