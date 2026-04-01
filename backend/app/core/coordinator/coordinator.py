"""Coordinator - 多 Agent 协调器

Coordinator 负责管理和调度多个 Worker，支持并行执行和结果聚合。
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar
from collections import defaultdict

from .worker import Worker, WorkerStatus, WorkerResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Coordinator:
    """Coordinator - 多 Agent 协调器

    负责：
    - 创建和管理 Worker
    - 并行执行多个 Worker
    - 聚合执行结果
    - 处理失败和重试

    典型使用场景：
    - 并行调用多个独立 API（天气、地图、POI）
    - 多个 Agent 同时处理不同子任务
    - 研究型任务：先收集信息，再综合处理
    """

    def __init__(self, name: Optional[str] = None):
        """初始化 Coordinator

        Args:
            name: Coordinator 名称，用于日志
        """
        self._name = name or "Coordinator"
        self._workers: Dict[str, Worker] = {}
        self._results: Dict[str, WorkerResult] = {}
        logger.info(f"[{self._name}] Initialized")

    @property
    def name(self) -> str:
        """获取 Coordinator 名称"""
        return self._name

    @property
    def workers(self) -> List[Worker]:
        """获取所有已注册的 Worker"""
        return list(self._workers.values())

    @property
    def results(self) -> Dict[str, WorkerResult]:
        """获取所有执行结果"""
        return self._results.copy()

    def create_worker(
        self,
        task_id: str,
        description: str,
        execute_fn: Optional[Callable[..., Any]] = None,
        is_concurrent_safe: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Worker:
        """创建并注册一个 Worker

        Args:
            task_id: 任务唯一标识
            description: 任务描述
            execute_fn: 执行函数
            is_concurrent_safe: 是否可安全并发执行
            metadata: 额外的元数据

        Returns:
            Worker: 创建的 Worker 实例

        Raises:
            ValueError: 如果 task_id 已存在
        """
        if task_id in self._workers:
            raise ValueError(f"Worker with task_id '{task_id}' already exists")

        worker = Worker(
            task_id=task_id,
            description=description,
            execute_fn=execute_fn,
            is_concurrent_safe=is_concurrent_safe,
            metadata=metadata,
        )

        self._workers[task_id] = worker
        logger.info(f"[{self._name}] Created worker: {task_id}")

        return worker

    def register_worker(self, worker: Worker) -> None:
        """注册一个已存在的 Worker

        Args:
            worker: 要注册的 Worker

        Raises:
            ValueError: 如果 task_id 已存在
        """
        if worker.task_id in self._workers:
            raise ValueError(f"Worker with task_id '{worker.task_id}' already exists")

        self._workers[worker.task_id] = worker
        logger.info(f"[{self._name}] Registered worker: {worker.task_id}")

    def get_worker(self, task_id: str) -> Optional[Worker]:
        """获取指定的 Worker

        Args:
            task_id: 任务 ID

        Returns:
            Worker 或 None
        """
        return self._workers.get(task_id)

    def remove_worker(self, task_id: str) -> Optional[Worker]:
        """移除指定的 Worker

        Args:
            task_id: 任务 ID

        Returns:
            被移除的 Worker，如果不存在则返回 None
        """
        worker = self._workers.pop(task_id, None)
        if worker:
            # 同时清理结果
            self._results.pop(task_id, None)
            logger.info(f"[{self._name}] Removed worker: {task_id}")
        return worker

    def clear_workers(self) -> None:
        """清空所有 Worker"""
        self._workers.clear()
        self._results.clear()
        logger.info(f"[{self._name}] Cleared all workers")

    async def run_parallel(
        self,
        task_ids: Optional[List[str]] = None,
        fail_fast: bool = False,
        **kwargs
    ) -> Dict[str, WorkerResult]:
        """并行执行多个 Worker

        Args:
            task_ids: 要执行的任务 ID 列表，为 None 时执行所有已注册的 Worker
            fail_fast: 是否在第一个失败时立即停止
            **kwargs: 传递给每个 Worker 的参数

        Returns:
            任务 ID 到执行结果的映射
        """
        # 确定要执行的任务
        if task_ids is None:
            target_ids = list(self._workers.keys())
        else:
            target_ids = task_ids

        if not target_ids:
            logger.warning(f"[{self._name}] No workers to execute")
            return {}

        # 获取目标 Workers
        workers_to_run = []
        for task_id in target_ids:
            worker = self._workers.get(task_id)
            if worker is None:
                logger.warning(f"[{self._name}] Worker '{task_id}' not found, skipping")
                continue
            workers_to_run.append(worker)

        if not workers_to_run:
            return {}

        logger.info(
            f"[{self._name}] Running {len(workers_to_run)} workers in parallel"
        )

        # 创建执行任务
        tasks = [worker.execute(**kwargs) for worker in workers_to_run]

        if fail_fast:
            # 使用 return_exceptions=False，第一个错误会立即抛出
            results = await asyncio.gather(*tasks, return_exceptions=False)
        else:
            # 使用 return_exceptions=True，收集所有结果（包括错误）
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        output: Dict[str, WorkerResult] = {}
        for i, result in enumerate(results):
            worker = workers_to_run[i]

            if isinstance(result, Exception):
                # 创建失败结果
                output[worker.task_id] = WorkerResult(
                    task_id=worker.task_id,
                    status=WorkerStatus.FAILED,
                    error=result,
                )
            else:
                output[worker.task_id] = result

        # 更新内部结果缓存
        self._results.update(output)

        # 统计
        success_count = sum(1 for r in output.values() if r.is_success)
        failure_count = len(output) - success_count

        logger.info(
            f"[{self._name}] Parallel execution completed: "
            f"{success_count} success, {failure_count} failed"
        )

        return output

    async def run_sequence(
        self,
        task_ids: List[str],
        **kwargs
    ) -> List[WorkerResult]:
        """按顺序串行执行多个 Worker

        Args:
            task_ids: 要执行的任务 ID 列表（按顺序）
            **kwargs: 传递给每个 Worker 的参数

        Returns:
            执行结果列表（按执行顺序）
        """
        results = []

        logger.info(f"[{self._name}] Running {len(task_ids)} workers in sequence")

        for task_id in task_ids:
            worker = self._workers.get(task_id)
            if worker is None:
                logger.warning(f"[{self._name}] Worker '{task_id}' not found, skipping")
                continue

            logger.info(f"[{self._name}] Executing worker: {task_id}")
            result = await worker.execute(**kwargs)
            results.append(result)

            # 更新缓存
            self._results[task_id] = result

        return results

    async def process_with_research(
        self,
        research_task_id: str,
        synthesis_task_id: str,
        research_params: Optional[Dict[str, Any]] = None,
        synthesis_params: Optional[Dict[str, Any]] = None,
    ) -> WorkerResult:
        """执行研究型任务：先收集信息，再综合处理

        典型模式：
        1. Research Worker 收集信息（并行调用多个 API）
        2. Synthesis Worker 综合信息并生成最终结果

        Args:
            research_task_id: 研究任务 ID
            synthesis_task_id: 综合任务 ID
            research_params: 研究任务参数
            synthesis_params: 综合任务参数

        Returns:
            综合任务的执行结果

        Raises:
            ValueError: 如果指定的 Worker 不存在
        """
        research_worker = self._workers.get(research_task_id)
        synthesis_worker = self._workers.get(synthesis_task_id)

        if research_worker is None:
            raise ValueError(f"Research worker '{research_task_id}' not found")
        if synthesis_worker is None:
            raise ValueError(f"Synthesis worker '{synthesis_task_id}' not found")

        logger.info(
            f"[{self._name}] Starting research workflow: "
            f"{research_task_id} -> {synthesis_task_id}"
        )

        # Step 1: 执行研究任务
        research_params = research_params or {}
        research_result = await research_worker.execute(**research_params)

        if not research_result.is_success:
            logger.error(f"[{self._name}] Research task failed: {research_result.error}")
            return research_result

        logger.info(f"[{self._name}] Research completed, starting synthesis")

        # Step 2: ���行综合任务，传入研究结果
        synthesis_params = synthesis_params or {}
        synthesis_params["research_output"] = research_result.output

        synthesis_result = await synthesis_worker.execute(**synthesis_params)

        # 更新缓存
        self._results[research_task_id] = research_result
        self._results[synthesis_task_id] = synthesis_result

        logger.info(f"[{self._name}] Research workflow completed")

        return synthesis_result

    def get_status_summary(self) -> Dict[str, Any]:
        """获取所有 Worker 的状态摘要

        Returns:
            状态摘要字典
        """
        status_counts = defaultdict(int)

        for worker in self._workers.values():
            status_counts[worker.status.value] += 1

        return {
            "total_workers": len(self._workers),
            "status_breakdown": dict(status_counts),
            "results_count": len(self._results),
            "success_count": sum(1 for r in self._results.values() if r.is_success),
            "failure_count": sum(1 for r in self._results.values() if r.is_failure),
        }

    def reset_all(self) -> None:
        """重置所有 Worker 状态"""
        for worker in self._workers.values():
            worker.reset()
        self._results.clear()
        logger.info(f"[{self._name}] Reset all workers")

    def __repr__(self) -> str:
        return f"Coordinator(name={self._name}, workers={len(self._workers)})"


def create_worker(
    task_id: str,
    description: str,
    execute_fn: Optional[Callable[..., Any]] = None,
    is_concurrent_safe: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> Worker:
    """创建 Worker 的工厂函数

    这是一个便捷函数，用于创建 Worker 而不需要直接使用 Coordinator。

    Args:
        task_id: 任务唯一标识
        description: 任务描述
        execute_fn: 执行函数
        is_concurrent_safe: 是否可安全并发执行
        metadata: 额外的元数据

    Returns:
        Worker: 创建的 Worker 实例

    Example:
        >>> worker = create_worker(
        ...     task_id="weather_check",
        ...     description="Check weather for destination",
        ...     execute_fn=lambda city: f"Weather in {city}",
        ... )
        >>> result = await worker.execute(city="Beijing")
    """
    return Worker(
        task_id=task_id,
        description=description,
        execute_fn=execute_fn,
        is_concurrent_safe=is_concurrent_safe,
        metadata=metadata,
    )


__all__ = [
    "Coordinator",
    "create_worker",
]
