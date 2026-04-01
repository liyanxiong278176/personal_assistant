"""Worker - 多 Agent 协调中的工作单元

Worker 代表一个独立的任务执行单元，可以被 Coordinator 调度。
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkerStatus(str, Enum):
    """Worker 状态"""
    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 执行失败
    CANCELLED = "cancelled"  # 已取消


class WorkerResult:
    """Worker 执行结果

    封装 Worker 的执行结果，包含状态、输出和错误信息。
    """

    def __init__(
        self,
        task_id: str,
        status: WorkerStatus,
        output: Optional[Any] = None,
        error: Optional[Exception] = None,
        execution_time: Optional[float] = None,
    ):
        """初始化 WorkerResult

        Args:
            task_id: 任务 ID
            status: 执行状态
            output: 执行输出（成功时）
            error: 错误信息（失败时）
            execution_time: 执行耗时（秒）
        """
        self.task_id = task_id
        self.status = status
        self.output = output
        self.error = error
        self.execution_time = execution_time
        self.completed_at = datetime.now()

    @property
    def is_success(self) -> bool:
        """是否执行成功"""
        return self.status == WorkerStatus.COMPLETED

    @property
    def is_failure(self) -> bool:
        """是否执行失败"""
        return self.status == WorkerStatus.FAILED

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            包含结果信息的字典
        """
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": str(self.error) if self.error else None,
            "execution_time": self.execution_time,
            "completed_at": self.completed_at.isoformat(),
        }


class Worker:
    """Worker - 任务执行单元

    Worker 是一个可被调度的任务单元，封装了：
    - 任务 ID 和描述
    - 执行逻辑（execute 方法）
    - 当前状态
    - 执行结果

    可用于实现多 Agent 协调模式，多个 Worker 可以并行执行。
    """

    def __init__(
        self,
        task_id: str,
        description: str,
        execute_fn: Optional[Callable[..., Any]] = None,
        is_concurrent_safe: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """初始化 Worker

        Args:
            task_id: 任务唯一标识
            description: 任务描述
            execute_fn: 执行函数，为 None 时需要子类覆盖 execute 方法
            is_concurrent_safe: 是否可安全并发执行
            metadata: 额外的元数据
        """
        self._task_id = task_id
        self._description = description
        self._execute_fn = execute_fn
        self._is_concurrent_safe = is_concurrent_safe
        self._metadata = metadata or {}
        self._status = WorkerStatus.PENDING
        self._result: Optional[WorkerResult] = None

    @property
    def task_id(self) -> str:
        """获取任务 ID"""
        return self._task_id

    @property
    def description(self) -> str:
        """获取任务描述"""
        return self._description

    @property
    def status(self) -> WorkerStatus:
        """获取当前状态"""
        return self._status

    @property
    def is_concurrent_safe(self) -> bool:
        """是否可安全并发执行"""
        return self._is_concurrent_safe

    @property
    def result(self) -> Optional[WorkerResult]:
        """获取执行结果"""
        return self._result

    @property
    def metadata(self) -> Dict[str, Any]:
        """获取元数据"""
        return self._metadata.copy()

    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据

        Args:
            key: 元数据键
            value: 元数据值
        """
        self._metadata[key] = value

    async def execute(self, **kwargs) -> WorkerResult:
        """执行任务

        如果提供了 execute_fn，则调用它；否则由子类实现。

        Args:
            **kwargs: 执行参数

        Returns:
            WorkerResult: 执行结果

        Raises:
            RuntimeError: 如果 execute_fn 未提供且子类未覆盖
        """
        if self._execute_fn is None:
            raise RuntimeError(
                f"Worker {self._task_id}: No execute function provided. "
                "Either provide execute_fn or subclass Worker and override execute()."
            )

        self._status = WorkerStatus.RUNNING
        logger.info(f"[Worker:{self._task_id}] Starting execution")

        start_time = asyncio.get_event_loop().time()
        error = None
        output = None

        try:
            # 执行任务函数
            if asyncio.iscoroutinefunction(self._execute_fn):
                output = await self._execute_fn(**kwargs)
            else:
                output = self._execute_fn(**kwargs)

            self._status = WorkerStatus.COMPLETED
            logger.info(f"[Worker:{self._task_id}] Completed successfully")

        except Exception as e:
            self._status = WorkerStatus.FAILED
            error = e
            logger.error(f"[Worker:{self._task_id}] Failed with error: {e}")

        execution_time = asyncio.get_event_loop().time() - start_time

        # 创建结果对象
        self._result = WorkerResult(
            task_id=self._task_id,
            status=self._status,
            output=output,
            error=error,
            execution_time=execution_time,
        )

        return self._result

    def cancel(self) -> None:
        """取消任务（标记为已取消）

        注意：这只是状态标记，不会中断正在执行的任务。
        实际的中断需要额外的实现。
        """
        if self._status == WorkerStatus.PENDING:
            self._status = WorkerStatus.CANCELLED
            logger.info(f"[Worker:{self._task_id}] Cancelled")
        else:
            logger.warning(
                f"[Worker:{self._task_id}] Cannot cancel worker in {self._status} state"
            )

    def reset(self) -> None:
        """重置 Worker 状态，允许重新执行"""
        self._status = WorkerStatus.PENDING
        self._result = None
        logger.debug(f"[Worker:{self._task_id}] Reset")

    def __repr__(self) -> str:
        return f"Worker(id={self._task_id}, status={self._status.value})"


__all__ = [
    "Worker",
    "WorkerStatus",
    "WorkerResult",
]
