"""灰度放量与版本管理

UC8-1 改进: 添加灰度放量开关、版本检测和降级回滚机制
"""

import logging
import hashlib
import time
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ReleaseState(Enum):
    """发布状态"""
    STABLE = "stable"        # 稳定版本
    BETA = "beta"            # 灰度版本
    ROLLBACK = "rollback"     # 回滚中


@dataclass
class VersionInfo:
    """版本信息"""
    version: str
    release_state: ReleaseState
    rollout_percentage: float  # 0.0-1.0
    min_version: Optional[str]  # 最低兼容版本
    created_at: float
    rollout_start: Optional[float]


class FeatureFlagManager:
    """功能开关管理器

    支持：
    - 灰度放量百分比控制
    - 用户分组隔离
    - 版本回滚
    """

    # 当前版本信息
    CURRENT_VERSION = "1.0.0"

    def __init__(self):
        self._flags: Dict[str, VersionInfo] = {}
        self._user_assignments: Dict[str, str] = {}  # user_id -> version
        self._rollback_history: list = []
        self._max_rollback_history = 10

        # 注册当前稳定版本
        self.register_version(
            version=self.CURRENT_VERSION,
            state=ReleaseState.STABLE,
            rollout=1.0
        )

        logger.info(
            f"[FeatureFlags] 初始化完成 | "
            f"version={self.CURRENT_VERSION} | state=STABLE"
        )

    def register_version(
        self,
        version: str,
        state: ReleaseState,
        rollout: float = 1.0,
        min_version: Optional[str] = None
    ) -> None:
        """注册新版本

        Args:
            version: 版本号
            state: 发布状态
            rollout: 灰度放量百分比 (0.0-1.0)
            min_version: 最低兼容版本
        """
        info = VersionInfo(
            version=version,
            release_state=state,
            rollout_percentage=rollout,
            min_version=min_version,
            created_at=time.time(),
            rollout_start=time.time() if rollout < 1.0 else None
        )
        self._flags[version] = info

        logger.info(
            f"[FeatureFlags] 注册版本 | "
            f"version={version} | state={state.value} | rollout={rollout*100:.0f}%"
        )

    def is_user_in_rollout(self, user_id: str, feature: str) -> bool:
        """判断用户是否在灰度放量范围内

        Args:
            user_id: 用户ID
            feature: 功能名称

        Returns:
            True 如果用户应该使用新版本
        """
        if not user_id:
            return True  # 无用户ID，默认使用新版本

        # 获取用户的版本分配
        version = self._get_user_version(user_id)
        version_info = self._flags.get(version)

        if not version_info:
            logger.warning(f"[FeatureFlags] 未知版本: {version}")
            return True

        if version_info.release_state == ReleaseState.ROLLBACK:
            return False

        if version_info.release_state == ReleaseState.STABLE:
            return True

        # BETA状态：根据灰度百分比决定
        user_hash = int(hashlib.md5(f"{user_id}:{feature}".encode()).hexdigest(), 16)
        in_rollout = (user_hash % 100) < (version_info.rollout_percentage * 100)

        logger.debug(
            f"[FeatureFlags] 灰度判断 | "
            f"user={user_id[:8]}... | feature={feature} | "
            f"in_rollout={in_rollout} | percentage={version_info.rollout_percentage*100:.0f}%"
        )

        return in_rollout

    def _get_user_version(self, user_id: str) -> str:
        """获取用户被分配的版本"""
        return self._user_assignments.get(user_id, self.CURRENT_VERSION)

    def set_user_version(self, user_id: str, version: str) -> None:
        """手动设置用户的版本（用于测试或特定用户）"""
        self._user_assignments[user_id] = version
        logger.info(
            f"[FeatureFlags] 设置用户版本 | "
            f"user={user_id[:8]}... | version={version}"
        )

    def rollback(self, target_version: Optional[str] = None) -> bool:
        """回滚到指定版本或上一稳定版本

        Args:
            target_version: 目标版本，None则回滚到上一稳定版本

        Returns:
            True 如果回滚成功
        """
        # 记录回滚历史
        rollback_record = {
            "timestamp": time.time(),
            "current_version": self.CURRENT_VERSION,
            "target_version": target_version,
            "reason": "manual_rollback"
        }

        # 确定目标版本
        if target_version is None:
            # 查找上一稳定版本
            for version, info in sorted(
                self._flags.items(),
                key=lambda x: x[1].created_at,
                reverse=True
            ):
                if info.release_state == ReleaseState.STABLE:
                    target_version = version
                    break

        if target_version and target_version in self._flags:
            # 更新所有灰度版本为回滚状态
            for version, info in self._flags.items():
                if info.release_state == ReleaseState.BETA:
                    info.release_state = ReleaseState.ROLLBACK

            # 注册回滚后的稳定版本
            self.register_version(
                version=target_version,
                state=ReleaseState.STABLE,
                rollout=1.0
            )

            rollback_record["success"] = True
            rollback_record["target_version"] = target_version

            self._rollback_history.append(rollback_record)
            if len(self._rollback_history) > self._max_rollback_history:
                self._rollback_history.pop(0)

            logger.warning(
                f"[FeatureFlags] ⚡ 版本回滚完成 | "
                f"from={self.CURRENT_VERSION} | to={target_version}"
            )
            return True

        logger.error(f"[FeatureFlags] 回滚失败: 目标版本不存在")
        return False

    def gradual_rollout(
        self,
        version: str,
        target_percentage: float,
        step: float = 0.1
    ) -> None:
        """渐进式放量

        Args:
            version: 版本号
            target_percentage: 目标放量百分比 (0.0-1.0)
            step: 每次增加的百分比
        """
        if version not in self._flags:
            logger.warning(f"[FeatureFlags] 未知版本: {version}")
            return

        info = self._flags[version]
        current = info.rollout_percentage

        while current < target_percentage:
            current = min(current + step, target_percentage)
            info.rollout_percentage = round(current, 2)

            logger.info(
                f"[FeatureFlags] 📈 灰度放量 | "
                f"version={version} | {current*100:.0f}%"
            )

            # 实际使用中可以这里触发监控告警
            time.sleep(0.1)  # 避免太快

    def get_version_info(self, version: Optional[str] = None) -> Optional[VersionInfo]:
        """获取版本信息"""
        v = version or self.CURRENT_VERSION
        return self._flags.get(v)

    def get_all_versions(self) -> Dict[str, VersionInfo]:
        """获取所有版本信息"""
        return self._flags.copy()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stable = sum(1 for v in self._flags.values() if v.release_state == ReleaseState.STABLE)
        beta = sum(1 for v in self._flags.values() if v.release_state == ReleaseState.BETA)

        return {
            "current_version": self.CURRENT_VERSION,
            "stable_versions": stable,
            "beta_versions": beta,
            "total_users_assigned": len(self._user_assignments),
            "rollback_history": self._rollback_history
        }


# 全局实例
_feature_flag_manager: Optional[FeatureFlagManager] = None


def get_feature_flag_manager() -> FeatureFlagManager:
    global _feature_flag_manager
    if _feature_flag_manager is None:
        _feature_flag_manager = FeatureFlagManager()
    return _feature_flag_manager


def is_feature_enabled(user_id: str, feature: str) -> bool:
    """便捷函数：判断功能是否对用户启用"""
    return get_feature_flag_manager().is_user_in_rollout(user_id, feature)


__all__ = [
    "ReleaseState", "VersionInfo", "FeatureFlagManager",
    "get_feature_flag_manager", "is_feature_enabled"
]
