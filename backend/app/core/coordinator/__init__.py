"""Coordinator 包 - 多 Agent 协调

提供 Coordinator 和 Worker 模式，用于多 Agent 协调和并行任务执行。
"""

from .worker import Worker, WorkerStatus, WorkerResult
from .coordinator import Coordinator, create_worker

__all__ = [
    "Worker",
    "WorkerStatus",
    "WorkerResult",
    "Coordinator",
    "create_worker",
]
