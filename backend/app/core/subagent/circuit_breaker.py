"""熔断器 - 防止级联故障

当工具/服务连续失败达到阈值时，暂时停止调用，避免雪崩。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常状态，允许请求
    OPEN = "open"           # 熔断状态，拒绝请求
    HALF_OPEN = "half_open" # 半开状态，允许尝试


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5      # 失败阈值
    success_threshold: int = 2     # 半开状态成功阈值
    timeout: float = 60.0          # 熔断持续时间（秒）
    half_open_max_calls: int = 3   # 半开状态最大尝试次数


@dataclass
class CallResult:
    """调用结果"""
    success: bool
    latency_ms: float
    error: Optional[Exception] = None


class CircuitBreaker:
    """熔断器

    三种状态转换：
    CLOSED → OPEN: 失败数达到阈值
    OPEN → HALF_OPEN: 冷却时间结束
    HALF_OPEN → CLOSED: 连续成功达到阈值
    HALF_OPEN → OPEN: 再次失败
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()

        # 状态
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None

        # 半开状态控制
        self._half_open_calls = 0

        # 统计
        self._total_calls = 0
        self._total_failures = 0

        logger.info(
            f"[CIRCUIT_BREAKER] 🛡️ 初始化 | "
            f"name={name} | "
            f"failure_threshold={self.config.failure_threshold}"
        )

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        # 检查是否需要从 OPEN 转为 HALF_OPEN
        if self._state == CircuitState.OPEN:
            if self._opened_at and (time.time() - self._opened_at) >= self.config.timeout:
                logger.info(
                    f"[CIRCUIT_BREAKER] ⏰ 熔断时间结束 | "
                    f"name={self.name} | OPEN → HALF_OPEN"
                )
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0

        return self._state

    def allow_request(self) -> bool:
        """检查是否允许请求

        Returns:
            True 如果允许，False 否则（熔断中）
        """
        current_state = self.state

        if current_state == CircuitState.CLOSED:
            return True

        if current_state == CircuitState.OPEN:
            logger.warning(
                f"[CIRCUIT_BREAKER] 🚫 熔断中 | "
                f"name={self.name} | "
                f"failure_count={self._failure_count}/{self.config.failure_threshold}"
            )
            return False

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.config.half_open_max_calls:
                logger.warning(
                    f"[CIRCUIT_BREAKER] 🚫 半开尝试次数耗尽 | "
                    f"name={self.name} | "
                    f"calls={self._half_open_calls}/{self.config.half_open_max_calls}"
                )
                return False
            self._half_open_calls += 1

        return True

    def record_success(self, latency_ms: float = 0):
        """记录成功调用"""
        self._total_calls += 1
        self._success_count += 1

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下连续成功，恢复为关闭
            if self._success_count >= self.config.success_threshold:
                logger.info(
                    f"[CIRCUIT_BREAKER] ✅ 恢复正常 | "
                    f"name={self.name} | "
                    f"HALF_OPEN → CLOSED | "
                    f"success_count={self._success_count}"
                )
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0

    def record_failure(self, error: Exception):
        """记录失败调用"""
        self._total_calls += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()

        # 检查是否需要熔断
        if self._failure_count >= self.config.failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.error(
                    f"[CIRCUIT_BREAKER] ⚡ 熔断触发 | "
                    f"name={self.name} | "
                    f"failure_count={self._failure_count}/{self.config.failure_threshold} | "
                    f"error={error}"
                )
                self._state = CircuitState.OPEN
                self._opened_at = time.time()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "failure_rate": (
                self._total_failures / self._total_calls
                if self._total_calls > 0 else 0
            ),
            "opened_at": (
                datetime.fromtimestamp(self._opened_at).isoformat()
                if self._opened_at else None
            )
        }


class CircuitBreakerRegistry:
    """熔断器注册表"""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._config = CircuitBreakerConfig()

    def get_breaker(self, name: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, self._config)
            logger.info(f"[CIRCUIT_BREAKER] 📦 创建熔断器 | name={name}")
        return self._breakers[name]

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有熔断器的统计"""
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }


# 全局熔断器注册表
_global_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """获取全局熔断器注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = CircuitBreakerRegistry()
    return _global_registry


__all__ = [
    "CircuitState", "CircuitBreakerConfig", "CallResult",
    "CircuitBreaker", "CircuitBreakerRegistry",
    "get_circuit_breaker_registry"
]
