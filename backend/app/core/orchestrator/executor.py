"""Executor - 执行引擎：按计划执行工具并处理降级"""

import asyncio
import logging
from typing import Dict, Any, Optional

from .planner import ExecutionPlan, ExecutionStep, FallbackStrategy
from ..tools import ToolRegistry, global_registry

logger = logging.getLogger(__name__)


class Executor:
    """执行引擎 - 按计划执行工具并处理降级"""

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        cache: Any | None = None,
        fallback_handler: Any | None = None
    ):
        self._registry = tool_registry or global_registry
        self._cache = cache
        self._fallback_handler = fallback_handler
        self.logger = logging.getLogger(__name__)

    async def execute(
        self,
        plan: ExecutionPlan,
        llm_client: Any | None = None
    ) -> Dict[str, Any]:
        """执行计划

        Args:
            plan: 执行计划
            llm_client: LLM客户端（用于工具循环）

        Returns:
            工具名称到执行结果的映射
        """
        logger.info(f"[Executor] Starting plan execution: intent={plan.intent}, total_steps={len(plan.steps)}")
        results = {}

        # 并行执行无依赖的步骤
        for step in plan.steps:
            try:
                result = await self._execute_step(step)
                results[step.tool_name] = result
            except Exception as e:
                logger.error(f"[Executor] Step failed: tool={step.tool_name}, params={step.params}, error={e}")
                if step.can_fail:
                    logger.warning(f"[Executor] Attempting fallback: tool={step.tool_name}, fallback_strategy={step.fallback_strategy.value}")
                    # 尝试降级，传入计划级别的降级策略作为后备
                    result = await self._handle_fallback(step, e, plan.fallback_strategy)
                    results[step.tool_name] = result
                else:
                    logger.error(f"[Executor] Step is non-failable, raising: tool={step.tool_name}")
                    raise

        logger.info(f"[Executor] Plan execution completed: intent={plan.intent}, completed_steps={len(results)}, success_count={sum(1 for r in results.values() if r.get('success'))}")
        return results

    async def _execute_step(self, step: ExecutionStep) -> Dict[str, Any]:
        """执行单个步骤"""
        tool = self._registry.get(step.tool_name)
        if not tool:
            logger.error(f"[Executor] Tool not found: {step.tool_name}")
            raise ValueError(f"Tool {step.tool_name} not found")

        start = asyncio.get_event_loop().time()
        logger.debug(f"[Executor] Executing step: tool={step.tool_name}, params={step.params}, timeout={step.timeout_ms}ms")
        result = await tool.execute(**step.params)
        latency_ms = (asyncio.get_event_loop().time() - start) * 1000

        logger.info(f"[Executor] Step executed: tool={step.tool_name}, latency={latency_ms:.1f}ms, success=True")
        return {
            "success": True,
            "data": result,
            "latency_ms": latency_ms,
            "from_cache": False
        }

    async def _handle_fallback(
        self,
        step: ExecutionStep,
        error: Exception,
        plan_fallback_strategy: FallbackStrategy = FallbackStrategy.CONTINUE
    ) -> Dict[str, Any]:
        """处理降级"""
        # 1. 简单重试
        if self._is_retryable(error):
            logger.warning(f"[Executor] Retrying step (retryable error): tool={step.tool_name}, error={error}")
            try:
                await asyncio.sleep(1)
                return await self._execute_step(step)
            except Exception as retry_err:
                logger.warning(f"[Executor] Retry failed: tool={step.tool_name}, retry_error={retry_err}")

        # 2. 尝试缓存 (检查步骤级策略，如果没有则使用计划级策略)
        effective_strategy = step.fallback_strategy
        # 如果步骤策略是CONTINUE（默认），则使用计划级策略
        if effective_strategy == FallbackStrategy.CONTINUE:
            effective_strategy = plan_fallback_strategy
        if self._cache and effective_strategy == FallbackStrategy.USE_CACHE:
            logger.debug(f"[Executor] Attempting cache fallback: tool={step.tool_name}")
            cached = await self._cache.get(
                step.tool_name,
                step.params,
                max_age=3600
            )
            if cached:
                logger.info(f"[Executor] Cache hit: tool={step.tool_name}")
                return {
                    "success": True,
                    "data": cached,
                    "latency_ms": 0,
                    "from_cache": True,
                    "warning": "数据来自缓存，可能不是最新"
                }
            else:
                logger.debug(f"[Executor] Cache miss: tool={step.tool_name}")

        # 3. 友好降级
        if self._fallback_handler:
            logger.warning(f"[Executor] Using friendly fallback: tool={step.tool_name}")
            fallback = self._fallback_handler.get_fallback(error)
            return {
                "success": False,
                "data": fallback.message,
                "latency_ms": 0,
                "from_cache": False,
                "error": str(error)
            }

        logger.error(f"[Executor] All fallbacks exhausted: tool={step.tool_name}, original_error={error}")
        return {
            "success": False,
            "data": None,
            "error": str(error)
        }

    def _is_retryable(self, error: Exception) -> bool:
        """判断错误是否可重试"""
        error_str = str(error).lower()
        retryable_keywords = ["timeout", "network", "rate limit", "429", "503"]
        return any(kw in error_str for kw in retryable_keywords)
