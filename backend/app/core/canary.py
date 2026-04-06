"""灰度放量控制器

实现基于一致性哈希的灰度放量机制，支持：
1. 按用户ID分配灰度版本
2. 动态调整灰度流量比例
3. 平滑切换避免流量抖动
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class ReleaseState(Enum):
    STABLE = "stable"       # 稳定版本
    CANARY = "canary"       # 灰度版本
    ROLLBACK = "rollback"   # 回滚中


@dataclass
class VersionConfig:
    """版本配置"""
    version: str
    traffic_ratio: float = 0.0  # 0.0 - 1.0
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


@dataclass
class CanaryResult:
    """灰度决策结果"""
    version: str
    state: ReleaseState
    is_canary: bool
    user_hash: int


class CanaryController:
    """灰度放量控制器

    使用一致性哈希确保同一用户始终访问同一版本，
    避免刷新页面导致版本切换的用户体验问题。

    用法:
        controller = CanaryController()
        controller.add_version("v2.0.0", traffic_ratio=0.2)  # 20%用户走灰度
        result = controller.decide_version(user_id="user-123")
        if result.is_canary:
            # 使用新版本
        else:
            # 使用稳定版本
    """

    def __init__(
        self,
        stable_version: str = "stable",
        default_canary_ratio: float = 0.1
    ):
        self._stable_version = stable_version
        self._default_canary_ratio = default_canary_ratio
        self._versions: Dict[str, VersionConfig] = {}
        self._enabled_features: Dict[str, bool] = {}
        self._feature_flags: Dict[str, Dict] = {}

        # 注册稳定版本
        self._versions[stable_version] = VersionConfig(
            version=stable_version,
            traffic_ratio=1.0,
            enabled=True
        )

        logger.info(
            f"[CANARY] 初始化完成 | "
            f"stable={stable_version} | "
            f"default_canary_ratio={default_canary_ratio}"
        )

    def add_version(
        self,
        version: str,
        traffic_ratio: float = 0.1,
        metadata: Optional[Dict] = None
    ) -> None:
        """添加灰度版本

        Args:
            version: 版本号
            traffic_ratio: 灰度流量比例 (0.0-1.0)
            metadata: 版本元数据
        """
        if version in self._versions:
            logger.warning(f"[CANARY] 版本已存在: {version}, 更新配置")
            self._versions[version].traffic_ratio = traffic_ratio
            self._versions[version].metadata = metadata or {}
            return

        self._versions[version] = VersionConfig(
            version=version,
            traffic_ratio=traffic_ratio,
            enabled=True,
            metadata=metadata or {}
        )

        logger.info(
            f"[CANARY] 添加灰度版本 | "
            f"version={version} | "
            f"traffic_ratio={traffic_ratio:.1%}"
        )

    def remove_version(self, version: str) -> bool:
        """移除灰度版本

        Args:
            version: 版本号

        Returns:
            是否成功移除
        """
        if version == self._stable_version:
            logger.error("[CANARY] 无法移除稳定版本")
            return False

        if version in self._versions:
            self._versions[version].enabled = False
            logger.info(f"[CANARY] 禁用版本: {version}")
            return True

        return False

    def decide_version(self, user_id: str) -> CanaryResult:
        """决定用户访问的版本

        使用一致性哈希确保同一用户始终访问同一版本。

        Args:
            user_id: 用户ID

        Returns:
            CanaryResult: 版本决策结果
        """
        if not user_id:
            return CanaryResult(
                version=self._stable_version,
                state=ReleaseState.STABLE,
                is_canary=False,
                user_hash=0
            )

        # 计算用户哈希
        user_hash = self._compute_hash(user_id)
        hash_percent = user_hash % 10000  # 0-9999

        # 遍历所有启用的灰度版本
        for version, config in sorted(
            self._versions.items(),
            key=lambda x: x[0]  # 按版本号排序
        ):
            if not config.enabled or version == self._stable_version:
                continue

            # 检查用户是否在灰度范围内
            threshold = int(config.traffic_ratio * 10000)
            if hash_percent < threshold:
                logger.debug(
                    f"[CANARY] 用户进入灰度组 | "
                    f"user_id={user_id[:8]}... | "
                    f"version={version} | "
                    f"hash={hash_percent}/{threshold}"
                )
                return CanaryResult(
                    version=version,
                    state=ReleaseState.CANARY,
                    is_canary=True,
                    user_hash=user_hash
                )

        # 默认稳定版本
        return CanaryResult(
            version=self._stable_version,
            state=ReleaseState.STABLE,
            is_canary=False,
            user_hash=user_hash
        )

    def _compute_hash(self, user_id: str) -> int:
        """计算用户ID的哈希值"""
        return int(hashlib.md5(user_id.encode()).hexdigest(), 16)

    async def rollback_to_version(
        self,
        target_version: str,
        reason: str = ""
    ) -> bool:
        """回滚到指定版本

        Args:
            target_version: 目标版本
            reason: 回滚原因

        Returns:
            是否成功回滚
        """
        if target_version not in self._versions:
            logger.error(f"[CANARY] 回滚失败，版本不存在: {target_version}")
            return False

        logger.warning(
            f"[CANARY] ⚡ 执行回滚 | "
            f"target={target_version} | "
            f"reason={reason}"
        )

        # 禁用所有非目标版本
        for version in self._versions:
            self._versions[version].enabled = (version == target_version)

        return True

    def get_stats(self) -> Dict:
        """获取灰度统计"""
        stats = {
            "stable_version": self._stable_version,
            "versions": [],
            "total_users_canary": 0,
        }

        for version, config in self._versions.items():
            # 估算灰度用户比例
            estimated_users = int(config.traffic_ratio * 100)
            stats["versions"].append({
                "version": version,
                "traffic_ratio": config.traffic_ratio,
                "enabled": config.enabled,
                "estimated_users_percent": estimated_users,
            })
            if version != self._stable_version:
                stats["total_users_canary"] += estimated_users

        return stats

    def enable_feature(self, feature_name: str, enabled: bool = True) -> None:
        """启用/禁用功能开关

        Args:
            feature_name: 功能名称
            enabled: 是否启用
        """
        self._enabled_features[feature_name] = enabled
        logger.info(f"[CANARY] 功能开关 | {feature_name}={'启用' if enabled else '禁用'}")

    def is_feature_enabled(self, feature_name: str) -> bool:
        """检查功能是否启用

        Args:
            feature_name: 功能名称

        Returns:
            是否启用
        """
        return self._enabled_features.get(feature_name, False)


# 全局灰度控制器实例
_canary_controller: Optional[CanaryController] = None


def get_canary_controller() -> CanaryController:
    """获取全局灰度控制器实例"""
    global _canary_controller
    if _canary_controller is None:
        _canary_controller = CanaryController()
    return _canary_controller


__all__ = [
    "CanaryController",
    "CanaryResult",
    "ReleaseState",
    "VersionConfig",
    "get_canary_controller",
]
