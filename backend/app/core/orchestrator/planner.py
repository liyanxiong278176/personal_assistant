"""Planner - 计划生成器：根据意图和槽位生成工具执行计划"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional

from ..intent.classifier import IntentResult
from ..intent.slot_extractor import SlotResult
from ..tools import global_registry

logger = logging.getLogger(__name__)


class FallbackStrategy(Enum):
    """降级策略"""
    FAIL_FAST = "fail_fast"           # 失败即终止
    CONTINUE = "continue"             # 继续执行
    USE_CACHE = "use_cache"           # 使用缓存


@dataclass
class ExecutionStep:
    """执行步骤"""
    tool_name: str
    params: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    can_fail: bool = False
    timeout_ms: int = 5000
    fallback_strategy: FallbackStrategy = FallbackStrategy.CONTINUE


@dataclass
class ExecutionPlan:
    """执行计划"""
    intent: str
    steps: List[ExecutionStep]
    fallback_strategy: FallbackStrategy
    estimated_cost: float = 0.0  # 预估token成本


class Planner:
    """计划生成器 - 分析意图并生成工具执行计划"""

    def __init__(self, tool_registry=None):
        self._registry = tool_registry or global_registry
        self.logger = logging.getLogger(__name__)

    async def create_plan(
        self,
        intent: IntentResult,
        slots: SlotResult,
        context: Dict[str, Any] | None = None
    ) -> ExecutionPlan:
        """创建执行计划

        Args:
            intent: 意图分类结果
            slots: 提取的槽位
            context: 额外上下文

        Returns:
            执行计划
        """
        logger.info(f"[Planner] Creating execution plan: intent={intent.intent}, destination={slots.destination}, destinations={slots.destinations}")
        steps = []

        if intent.intent == "query":
            # 查询类 - 单工具
            if slots.destination:
                if self._needs_weather(context):
                    steps.append(ExecutionStep(
                        tool_name="get_weather",
                        params={"city": slots.destination},
                        can_fail=True,
                        fallback_strategy=FallbackStrategy.USE_CACHE
                    ))
                    logger.debug(f"[Planner] Added step: tool=get_weather, city={slots.destination}")

        elif intent.intent == "itinerary":
            # 行程规划 - 多工具
            if slots.destination or slots.destinations:
                # 天气
                if self._needs_weather(context):
                    steps.append(ExecutionStep(
                        tool_name="get_weather",
                        params={"city": slots.destination, "days": 3},
                        can_fail=True,
                        fallback_strategy=FallbackStrategy.USE_CACHE
                    ))
                    logger.debug(f"[Planner] Added step: tool=get_weather, city={slots.destination}, days=3")
                # 景点
                steps.append(ExecutionStep(
                    tool_name="search_poi",
                    params={"keywords": "景点", "city": slots.destination},
                    can_fail=True
                ))
                logger.debug(f"[Planner] Added step: tool=search_poi, city={slots.destination}")
                # 路线（如果有多个地点）
                if slots.destinations and len(slots.destinations) > 1:
                    steps.append(ExecutionStep(
                        tool_name="plan_route",
                        params={"destinations": slots.destinations},
                        can_fail=True
                    ))
                    logger.debug(f"[Planner] Added step: tool=plan_route, destinations={slots.destinations}")

        fallback = FallbackStrategy.CONTINUE if steps else FallbackStrategy.FAIL_FAST
        logger.info(f"[Planner] Execution plan created: intent={intent.intent}, steps={len(steps)}, fallback_strategy={fallback.value}")

        return ExecutionPlan(
            intent=intent.intent,
            steps=steps,
            fallback_strategy=fallback
        )

    def _needs_weather(self, context: Dict[str, Any] | None) -> bool:
        """判断是否需要天气信息"""
        if not context:
            return True
        # 最近1小时查过天气就不重复查
        last_weather = context.get("last_weather_query")
        if last_weather:
            return time.time() - last_weather > 3600
        return True
