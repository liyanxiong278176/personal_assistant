"""评估器基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EvalMetrics:
    """评估指标基类"""
    total: int
    correct: int
    accuracy: float = 0.0

    def __post_init__(self):
        if self.total > 0:
            self.accuracy = self.correct / self.total


class BaseEvaluator(ABC):
    """评估器抽象基类"""

    @abstractmethod
    async def evaluate(self, **kwargs) -> EvalMetrics:
        """执行评估并返回指标

        Args:
            **kwargs: 子类可自定义参数

        Returns:
            EvalMetrics: 评估结果指标
        """
        pass
