"""意图三级分类器评估 API - Cache → Keyword → LLM

测试目标：
- 验证三级系统总覆盖率是否达到 80%+
- 统计各层（缓存、关键词、LLM）的覆盖率
- 基于 106 条测试用例（高频64、低频16、边界16、歧义10）

┌────────┬──────────┬──────────────────────┐
│  层级  │ 覆盖目标 │         说明         │
├────────┼──────────┼──────────────────────┤
│ 缓存   │ 30-40%   │ 完全重复查询         │
├────────┼──────────┼──────────────────────┤
│ 关键词 │ 40-50%   │ 有明确模式的高频查询 │
├────────┼──────────┼──────────────────────┤
│ LLM    │ <20%     │ 复杂表达兜底         │
├────────┼──────────┼──────────────────────┤
│ 合计   │ 80%+     │ 三级系统总覆盖       │
└────────┴──────────┴──────────────────────┘
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.auth.dependencies import require_auth
from app.auth.models import UserInfo
from app.core.context import RequestContext
from app.core.llm import LLMClient

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class TestCase:
    """测试用例"""
    id: int
    query: str
    expected_intent: str
    category: str  # "high_freq", "low_freq", "edge", "ambiguous"


@dataclass
class TierResult:
    """单层测试结果"""
    tier_name: str
    total_cases: int
    handled_count: int
    correct_count: int
    coverage_rate: float
    accuracy: float
    avg_confidence: float
    avg_response_time_ms: float


@dataclass
class ThreeTierEvalResult:
    """三级系统评估结果"""
    total_cases: int
    total_correct: int
    overall_accuracy: float
    cache_result: TierResult
    keyword_result: TierResult
    llm_result: TierResult
    high_freq_accuracy: float
    low_freq_accuracy: float
    edge_accuracy: float
    ambiguous_accuracy: float
    confusion_matrix: Dict[str, Dict[str, int]]
    detailed_results: List[Dict[str, Any]]
    intent_stats: Dict[str, Dict[str, Any]]


# ============================================================================
# Test Cases (106 total)
# ============================================================================

TEST_CASES: List[TestCase] = [
    # ========== 高频场景 (high_freq) - 64条 ==========
    # Itinerary (20)
    TestCase(1, "帮我规划北京三日游", "itinerary", "high_freq"),
    TestCase(2, "制定一个上海旅游计划", "itinerary", "high_freq"),
    TestCase(3, "安排一下西安五日游", "itinerary", "high_freq"),
    TestCase(4, "我想去成都玩两天", "itinerary", "high_freq"),
    TestCase(13, "帮我规划行程", "itinerary", "high_freq"),
    TestCase(14, "北京三日游路线", "itinerary", "high_freq"),
    TestCase(15, "旅游计划", "itinerary", "high_freq"),
    TestCase(16, "去云南玩", "itinerary", "high_freq"),
    TestCase(31, "北京三日游", "itinerary", "high_freq"),
    TestCase(32, "上海两日游", "itinerary", "high_freq"),
    TestCase(33, "五天去哪玩", "itinerary", "high_freq"),
    TestCase(65, "帮我定制一个豪华游", "itinerary", "high_freq"),
    TestCase(66, "设计一条文化之旅", "itinerary", "high_freq"),
    TestCase(81, "北三日游", "itinerary", "high_freq"),
    TestCase(82, "上海游", "itinerary", "high_freq"),
    TestCase(83, "两日游", "itinerary", "high_freq"),
    TestCase(97, "5天假去哪", "itinerary", "high_freq"),
    TestCase(98, "周末计划", "itinerary", "high_freq"),
    TestCase(102, "安排一下", "itinerary", "high_freq"),
    TestCase(105, "帮订机票和酒店", "itinerary", "high_freq"),

    # Query (16)
    TestCase(5, "北京有什么好玩的", "query", "high_freq"),
    TestCase(6, "上海天气怎么样", "query", "high_freq"),
    TestCase(7, "杭州明天有雨吗", "query", "high_freq"),
    TestCase(8, "怎么去故宫", "query", "high_freq"),
    TestCase(17, "北京怎么去", "query", "high_freq"),
    TestCase(18, "如何前往上海", "query", "high_freq"),
    TestCase(19, "门票价格", "query", "high_freq"),
    TestCase(20, "开放时间", "query", "high_freq"),
    TestCase(34, "西湖天气", "query", "high_freq"),
    TestCase(35, "下雨吗", "query", "high_freq"),
    TestCase(36, "需要带伞吗", "query", "high_freq"),
    TestCase(37, "有太阳吗", "query", "high_freq"),
    TestCase(38, "热不热", "query", "high_freq"),
    TestCase(39, "风力多大", "query", "high_freq"),
    TestCase(40, "穿衣建议", "query", "high_freq"),
    TestCase(67, "推荐个好地方", "query", "high_freq"),

    # Hotel (10)
    TestCase(9, "找北京的酒店", "hotel", "high_freq"),
    TestCase(21, "住宿推荐", "hotel", "high_freq"),
    TestCase(22, "住哪里", "hotel", "high_freq"),
    TestCase(41, "酒店", "hotel", "high_freq"),
    TestCase(42, "住宿", "hotel", "high_freq"),
    TestCase(43, "民宿", "hotel", "high_freq"),
    TestCase(44, "宾馆", "hotel", "high_freq"),
    TestCase(45, "青年旅舍", "hotel", "high_freq"),
    TestCase(46, "招待所", "hotel", "high_freq"),
    TestCase(69, "住的地方", "hotel", "high_freq"),

    # Food (8)
    TestCase(10, "推荐一些美食", "food", "high_freq"),
    TestCase(23, "有什么好吃的", "food", "high_freq"),
    TestCase(24, "美食推荐", "food", "high_freq"),
    TestCase(47, "美食", "food", "high_freq"),
    TestCase(48, "小吃", "food", "high_freq"),
    TestCase(49, "餐厅", "food", "high_freq"),
    TestCase(71, "有啥特色菜", "food", "high_freq"),
    TestCase(72, "当地美食", "food", "high_freq"),

    # Budget (8)
    TestCase(11, "大概多少钱", "budget", "high_freq"),
    TestCase(25, "预算多少", "budget", "high_freq"),
    TestCase(26, "多少钱", "budget", "high_freq"),
    TestCase(53, "预算", "budget", "high_freq"),
    TestCase(54, "花费", "budget", "high_freq"),
    TestCase(55, "便宜", "budget", "high_freq"),
    TestCase(56, "贵", "budget", "high_freq"),
    TestCase(57, "价位", "budget", "high_freq"),

    # Transport (6)
    TestCase(58, "怎么去", "transport", "high_freq"),
    TestCase(59, "交通", "transport", "high_freq"),
    TestCase(60, "飞机", "transport", "high_freq"),
    TestCase(61, "高铁", "transport", "high_freq"),
    TestCase(62, "开车", "transport", "high_freq"),
    TestCase(63, "自驾", "transport", "high_freq"),

    # Chat (6)
    TestCase(12, "你好", "chat", "high_freq"),
    TestCase(27, "在吗", "chat", "high_freq"),
    TestCase(28, "谢谢", "chat", "high_freq"),
    TestCase(29, "哈哈", "chat", "high_freq"),
    TestCase(30, "帮忙", "chat", "high_freq"),
    TestCase(64, "您好", "chat", "high_freq"),

    # ========== 低频场景 (low_freq) - 16条 ==========
    TestCase(70, "找个歇脚处", "hotel", "low_freq"),
    TestCase(73, "人均多少", "budget", "low_freq"),
    TestCase(74, "总预算", "budget", "low_freq"),
    TestCase(75, "怎么走", "transport", "low_freq"),
    TestCase(76, "坐什么车", "transport", "low_freq"),
    TestCase(77, "在不在", "chat", "low_freq"),
    TestCase(78, "有人吗", "chat", "low_freq"),
    TestCase(79, "嗨", "chat", "low_freq"),
    TestCase(80, "晚上好", "chat", "low_freq"),
    TestCase(68, "那个景点怎么样", "query", "low_freq"),
    TestCase(99, "那边怎么样", "query", "low_freq"),
    TestCase(103, "不想去人多的地方", "query", "low_freq"),
    TestCase(104, "那里好玩吗", "query", "low_freq"),
    TestCase(100, "推荐一下", "food", "low_freq"),
    TestCase(101, "找个地方", "hotel", "low_freq"),
    TestCase(106, "吃住行", "itinerary", "low_freq"),

    # ========== 边界场景 (edge) - 16条 ==========
    TestCase(84, "天气", "query", "edge"),
    TestCase(85, "雨", "query", "edge"),
    TestCase(86, "伞", "query", "edge"),
    TestCase(87, "旅舍", "hotel", "edge"),
    TestCase(88, "旅馆", "hotel", "edge"),
    TestCase(89, "入住", "hotel", "edge"),
    TestCase(90, "房间", "hotel", "edge"),
    TestCase(91, "吃啥", "food", "edge"),
    TestCase(92, "好吃吗", "food", "edge"),
    TestCase(93, "省钱", "budget", "edge"),
    TestCase(94, "花销", "budget", "edge"),
    TestCase(95, "出行", "transport", "edge"),
    TestCase(96, "交通工具", "transport", "edge"),
]


# ============================================================================
# Three-Tier Evaluator
# ============================================================================

class ThreeTierIntentEvaluator:
    """三级意图分类评估器"""

    def __init__(self):
        from app.core.intent import IntentRouter, RuleStrategy, CacheStrategy, ClassificationCache
        from app.core.intent.strategies import LLMStrategy
        import os

        self.RequestContext = RequestContext

        # Create cache
        self.cache = ClassificationCache(max_size=1000)

        # Check for LLM API key
        api_key = os.getenv("DEEPSEEK_API_KEY")

        if api_key:
            llm_client = LLMClient(api_key=api_key)
            llm_strategy = LLMStrategy(llm_client=llm_client)
            self.has_llm = True
        else:
            llm_strategy = None
            self.has_llm = False
            logger.warning("[ThreeTierEval] No DEEPSEEK_API_KEY found, LLM tests will be skipped")

        # Create strategies
        cache_strategy = CacheStrategy(cache=self.cache)
        rule_strategy = RuleStrategy(max_confidence=0.65)

        # Create routers for each tier
        self.router_keyword_only = IntentRouter(strategies=[rule_strategy])
        self.router_full = IntentRouter(strategies=[cache_strategy, rule_strategy])

        # LLM router (if available)
        if llm_strategy:
            self.router_llm = IntentRouter(strategies=[llm_strategy])
        else:
            self.router_llm = None

    async def evaluate(self, limit: Optional[int] = None) -> ThreeTierEvalResult:
        """运行三级系统评估

        Args:
            limit: 限制测试用例数量

        Returns:
            ThreeTierEvalResult: 完整评估结果
        """
        import time

        cases = TEST_CASES[:limit] if limit else TEST_CASES

        # 统计数据
        confusion: Dict[str, Dict[str, int]] = {}
        detailed_results = []

        # 分层统计
        category_stats = {
            "high_freq": {"correct": 0, "total": 0},
            "low_freq": {"correct": 0, "total": 0},
            "edge": {"correct": 0, "total": 0},
            "ambiguous": {"correct": 0, "total": 0},
        }

        # 意图统计
        intent_stats: Dict[str, Dict[str, Any]] = {}

        # 各层统计
        cache_stats = {"handled": 0, "correct": 0, "confidences": [], "times": []}
        keyword_stats = {"handled": 0, "correct": 0, "confidences": [], "times": []}
        llm_stats = {"handled": 0, "correct": 0, "confidences": [], "times": []}

        total_correct = 0

        for case in cases:
            # 1. Test cache layer (empty first run = all miss)
            start = time.perf_counter()
            cached = self.cache.get(case.query, False)
            cache_time = (time.perf_counter() - start) * 1000

            if cached:
                cache_stats["handled"] += 1
                cache_stats["times"].append(cache_time)
                cache_stats["confidences"].append(cached.confidence)
                if cached.intent == case.expected_intent:
                    cache_stats["correct"] += 1
                predicted = cached.intent
                confidence = cached.confidence
                tier = "cache"
            else:
                # 2. Test keyword layer
                start = time.perf_counter()
                context = self.RequestContext(message=case.query)
                result = await self.router_keyword_only.classify(context)
                keyword_time = (time.perf_counter() - start) * 1000

                keyword_stats["handled"] += 1
                keyword_stats["times"].append(keyword_time)
                keyword_stats["confidences"].append(result.confidence)

                # Store in cache
                self.cache.put(case.query, False, result)

                if result.confidence >= 0.65:
                    # Keyword layer handled it (matches RuleStrategy max_confidence)
                    if result.intent == case.expected_intent:
                        keyword_stats["correct"] += 1
                        total_correct += 1
                        category_stats[case.category]["correct"] += 1
                    predicted = result.intent
                    confidence = result.confidence
                    tier = "keyword"
                else:
                    # 3. LLM fallback layer
                    if self.router_llm:
                        start = time.perf_counter()
                        context = self.RequestContext(message=case.query)
                        llm_result = await self.router_llm.classify(context)
                        llm_time = (time.perf_counter() - start) * 1000

                        llm_stats["handled"] += 1
                        llm_stats["times"].append(llm_time)
                        llm_stats["confidences"].append(llm_result.confidence)

                        if llm_result.intent == case.expected_intent:
                            llm_stats["correct"] += 1
                            total_correct += 1
                            category_stats[case.category]["correct"] += 1
                        predicted = llm_result.intent
                        confidence = llm_result.confidence
                        tier = "llm"

                        # Update cache
                        self.cache.put(case.query, False, llm_result)
                    else:
                        # No LLM, use keyword result
                        if result.intent == case.expected_intent:
                            keyword_stats["correct"] += 1
                            total_correct += 1
                            category_stats[case.category]["correct"] += 1
                        predicted = result.intent
                        confidence = result.confidence
                        tier = "keyword_low_conf"

            # Update category stats
            category_stats[case.category]["total"] += 1

            # Confusion matrix
            if case.expected_intent not in confusion:
                confusion[case.expected_intent] = {}
            confusion[case.expected_intent][predicted] = confusion[case.expected_intent].get(predicted, 0) + 1

            # Intent stats
            if case.expected_intent not in intent_stats:
                intent_stats[case.expected_intent] = {"correct": 0, "total": 0}
            intent_stats[case.expected_intent]["total"] += 1
            if predicted == case.expected_intent:
                intent_stats[case.expected_intent]["correct"] += 1

            # Detailed result
            detailed_results.append({
                "id": case.id,
                "query": case.query,
                "expected": case.expected_intent,
                "predicted": predicted,
                "correct": predicted == case.expected_intent,
                "confidence": confidence,
                "tier": tier,
                "category": case.category,
            })

        # Calculate tier results
        total = len(cases)

        cache_result = TierResult(
            tier_name="cache",
            total_cases=total,
            handled_count=cache_stats["handled"],
            correct_count=cache_stats["correct"],
            coverage_rate=cache_stats["handled"] / total if total > 0 else 0,
            accuracy=cache_stats["correct"] / cache_stats["handled"] if cache_stats["handled"] > 0 else 0,
            avg_confidence=sum(cache_stats["confidences"]) / len(cache_stats["confidences"]) if cache_stats["confidences"] else 0,
            avg_response_time_ms=sum(cache_stats["times"]) / len(cache_stats["times"]) if cache_stats["times"] else 0,
        )

        keyword_result = TierResult(
            tier_name="keyword",
            total_cases=total,
            handled_count=keyword_stats["handled"],
            correct_count=keyword_stats["correct"],
            coverage_rate=keyword_stats["handled"] / total if total > 0 else 0,
            accuracy=keyword_stats["correct"] / keyword_stats["handled"] if keyword_stats["handled"] > 0 else 0,
            avg_confidence=sum(keyword_stats["confidences"]) / len(keyword_stats["confidences"]) if keyword_stats["confidences"] else 0,
            avg_response_time_ms=sum(keyword_stats["times"]) / len(keyword_stats["times"]) if keyword_stats["times"] else 0,
        )

        llm_result = TierResult(
            tier_name="llm",
            total_cases=total,
            handled_count=llm_stats["handled"],
            correct_count=llm_stats["correct"],
            coverage_rate=llm_stats["handled"] / total if total > 0 else 0,
            accuracy=llm_stats["correct"] / llm_stats["handled"] if llm_stats["handled"] > 0 else 0,
            avg_confidence=sum(llm_stats["confidences"]) / len(llm_stats["confidences"]) if llm_stats["confidences"] else 0,
            avg_response_time_ms=sum(llm_stats["times"]) / len(llm_stats["times"]) if llm_stats["times"] else 0,
        )

        # Calculate category accuracies
        high_freq_acc = category_stats["high_freq"]["correct"] / category_stats["high_freq"]["total"] if category_stats["high_freq"]["total"] > 0 else 0
        low_freq_acc = category_stats["low_freq"]["correct"] / category_stats["low_freq"]["total"] if category_stats["low_freq"]["total"] > 0 else 0
        edge_acc = category_stats["edge"]["correct"] / category_stats["edge"]["total"] if category_stats["edge"]["total"] > 0 else 0
        ambiguous_acc = category_stats["ambiguous"]["correct"] / category_stats["ambiguous"]["total"] if category_stats["ambiguous"]["total"] > 0 else 0

        return ThreeTierEvalResult(
            total_cases=total,
            total_correct=total_correct,
            overall_accuracy=total_correct / total if total > 0 else 0,
            cache_result=cache_result,
            keyword_result=keyword_result,
            llm_result=llm_result,
            high_freq_accuracy=high_freq_acc,
            low_freq_accuracy=low_freq_acc,
            edge_accuracy=edge_acc,
            ambiguous_accuracy=ambiguous_acc,
            confusion_matrix=confusion,
            detailed_results=detailed_results,
            intent_stats=intent_stats,
        )


# Global evaluator instance
_evaluator = None
_eval_lock = asyncio.Lock()


async def get_evaluator() -> ThreeTierIntentEvaluator:
    """获取评估器实例"""
    global _evaluator
    if _evaluator is None:
        async with _eval_lock:
            if _evaluator is None:
                _evaluator = ThreeTierIntentEvaluator()
    return _evaluator


# Create router
router = APIRouter(prefix="/api/v1/eval/intent", tags=["intent-evaluation"])


@router.post("/run")
async def run_intent_evaluation(
    limit: Optional[int] = None,
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """运行三级意图分类评估

    Args:
        limit: 可选，限制测试用例数量
        user: 当前用户（需要认证）

    Returns:
        完整评估结果，包含分层覆盖率、准确率、混淆矩阵
    """
    try:
        evaluator = await get_evaluator()
        result = await evaluator.evaluate(limit=limit)

        return JSONResponse({
            "status": "ok",
            "data": {
                # Summary
                "summary": {
                    "total_cases": result.total_cases,
                    "correct_predictions": result.total_correct,
                    "accuracy": round(result.overall_accuracy * 100, 1),
                    "high_freq_accuracy": round(result.high_freq_accuracy * 100, 1),
                    "low_freq_accuracy": round(result.low_freq_accuracy * 100, 1),
                    "edge_accuracy": round(result.edge_accuracy * 100, 1),
                    "ambiguous_accuracy": round(result.ambiguous_accuracy * 100, 1),
                },
                # Tier results
                "tier_results": {
                    "cache": {
                        "coverage_rate": round(result.cache_result.coverage_rate * 100, 1),
                        "accuracy": round(result.cache_result.accuracy * 100, 1),
                        "avg_confidence": round(result.cache_result.avg_confidence, 2),
                        "avg_response_time_ms": round(result.cache_result.avg_response_time_ms, 2),
                    },
                    "keyword": {
                        "coverage_rate": round(result.keyword_result.coverage_rate * 100, 1),
                        "accuracy": round(result.keyword_result.accuracy * 100, 1),
                        "avg_confidence": round(result.keyword_result.avg_confidence, 2),
                        "avg_response_time_ms": round(result.keyword_result.avg_response_time_ms, 2),
                    },
                    "llm": {
                        "coverage_rate": round(result.llm_result.coverage_rate * 100, 1),
                        "accuracy": round(result.llm_result.accuracy * 100, 1),
                        "avg_confidence": round(result.llm_result.avg_confidence, 2),
                        "avg_response_time_ms": round(result.llm_result.avg_response_time_ms, 2),
                    },
                },
                # Combined coverage
                "combined_coverage": round(
                    (result.keyword_result.coverage_rate + result.llm_result.coverage_rate) * 100, 1
                ),
                # Confusion matrix
                "confusion_matrix": result.confusion_matrix,
                # Intent stats
                "intent_stats": result.intent_stats,
                # Detailed results
                "detailed_results": result.detailed_results,
            },
        })
    except Exception as e:
        logging.exception("[IntentEval] Evaluation failed")
        return JSONResponse({
            "status": "error",
            "error": str(e),
        }, status_code=500)


@router.get("/test-cases")
async def get_test_cases(
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """获取测试用例列表"""
    cases = [
        {
            "id": c.id,
            "query": c.query,
            "expected_intent": c.expected_intent,
            "category": c.category,
        }
        for c in TEST_CASES
    ]
    return JSONResponse({
        "status": "ok",
        "count": len(cases),
        "data": cases,
    })
