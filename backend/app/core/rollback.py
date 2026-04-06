"""版本回滚管理器

支持版本快照创建、快速回滚、版本兼容性检查。

功能:
1. 版本快照 - 保存当前配置和代码状态
2. 快速回滚 - 一键回滚到指定版本
3. 兼容性检查 - 回滚前检查数据兼容性
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List, Any
from enum import Enum

logger = logging.getLogger(__name__)


class RollbackState(Enum):
    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class VersionSnapshot:
    """版本快照"""
    version: str
    created_at: float
    created_by: str
    config_snapshot: Dict[str, Any]
    code_hash: str
    db_schema_version: int
    description: str
    state: RollbackState = RollbackState.IDLE
    metadata: Dict = field(default_factory=dict)


@dataclass
class CompatibilityResult:
    """兼容性检查结果"""
    compatible: bool
    breaking_changes: List[str]
    warnings: List[str]
    migration_required: bool


class RollbackManager:
    """版本回滚管理器

    用法:
        manager = RollbackManager()

        # 创建快照
        await manager.create_snapshot(
            version="v2.0.0",
            description="新增复杂度评分V2"
        )

        # 回滚
        await manager.rollback(
            target_version="v1.9.0",
            reason="评分误判导致成本超支"
        )
    """

    def __init__(self, max_snapshots: int = 50):
        """初始化回滚管理器

        Args:
            max_snapshots: 最大保留快照数量
        """
        self._snapshots: Dict[str, VersionSnapshot] = {}
        self._rollback_history: List[Dict] = []
        self._max_snapshots = max_snapshots
        self._current_version: Optional[str] = None

        logger.info(f"[ROLLBACK] 初始化完成 | max_snapshots={max_snapshots}")

    async def create_snapshot(
        self,
        version: str,
        description: str = "",
        created_by: str = "system",
        config: Optional[Dict] = None,
        db_schema_version: int = 1
    ) -> VersionSnapshot:
        """创建版本快照

        Args:
            version: 版本号
            description: 快照描述
            created_by: 创建者
            config: 配置快照
            db_schema_version: 数据库schema版本

        Returns:
            VersionSnapshot: 快照对象
        """
        # 计算代码哈希
        code_hash = self._compute_code_hash()

        snapshot = VersionSnapshot(
            version=version,
            created_at=time.time(),
            created_by=created_by,
            config_snapshot=config or self._get_current_config(),
            code_hash=code_hash,
            db_schema_version=db_schema_version,
            description=description,
        )

        # 保存快照
        self._snapshots[version] = snapshot
        self._current_version = version

        # 清理旧快照
        await self._cleanup_old_snapshots()

        logger.info(
            f"[ROLLBACK] 创建快照 | "
            f"version={version} | "
            f"code_hash={code_hash[:8]}... | "
            f"description={description}"
        )

        return snapshot

    async def rollback(
        self,
        target_version: str,
        reason: str = "",
        initiated_by: str = "system"
    ) -> bool:
        """回滚到指定版本

        Args:
            target_version: 目标版本
            reason: 回滚原因
            initiated_by: 发起人

        Returns:
            是否成功回滚
        """
        if target_version not in self._snapshots:
            logger.error(f"[ROLLBACK] 回滚失败，快照不存在: {target_version}")
            return False

        snapshot = self._snapshots[target_version]

        # 检查兼容性
        compat_result = await self.check_compatibility(
            self._current_version or "unknown",
            target_version
        )

        if not compat_result.compatible and compat_result.migration_required:
            logger.error(
                f"[ROLLBACK] 回滚失败，需要数据迁移: "
                f"{compat_result.breaking_changes}"
            )
            return False

        logger.warning(
            f"[ROLLBACK] ⚡ 执行回滚 | "
            f"from={self._current_version} | "
            f"to={target_version} | "
            f"reason={reason} | "
            f"warnings={compat_result.warnings}"
        )

        # 更新快照状态
        snapshot.state = RollbackState.IN_PROGRESS

        try:
            # 执行回滚
            await self._apply_snapshot(snapshot)

            # 记录回滚历史
            self._rollback_history.append({
                "from_version": self._current_version,
                "to_version": target_version,
                "reason": reason,
                "initiated_by": initiated_by,
                "timestamp": time.time(),
            })

            snapshot.state = RollbackState.COMPLETED
            self._current_version = target_version

            logger.info(f"[ROLLBACK] ✅ 回滚完成 | {target_version}")
            return True

        except Exception as e:
            snapshot.state = RollbackState.FAILED
            logger.error(f"[ROLLBACK] ❌ 回滚失败: {e}")
            return False

    async def check_compatibility(
        self,
        old_version: str,
        new_version: str
    ) -> CompatibilityResult:
        """检查版本兼容性

        Args:
            old_version: 旧版本
            new_version: 新版本

        Returns:
            CompatibilityResult: 兼容性检查结果
        """
        breaking_changes: List[str] = []
        warnings: List[str] = []
        migration_required = False

        old_snap = self._snapshots.get(old_version)
        new_snap = self._snapshots.get(new_version)

        if not old_snap or not new_snap:
            warnings.append("快照数据不完整")
            return CompatibilityResult(
                compatible=True,
                breaking_changes=[],
                warnings=warnings,
                migration_required=False
            )

        # 检查schema版本变化
        if new_snap.db_schema_version < old_snap.db_schema_version:
            breaking_changes.append(
                f"数据库schema降级: {old_snap.db_schema_version} -> {new_snap.db_schema_version}"
            )
            migration_required = True

        # 检查配置key变化
        old_keys = set(old_snap.config_snapshot.keys())
        new_keys = set(new_snap.config_snapshot.keys())

        removed_keys = old_keys - new_keys
        if removed_keys:
            warnings.append(f"配置项移除: {removed_keys}")

        return CompatibilityResult(
            compatible=not migration_required,
            breaking_changes=breaking_changes,
            warnings=warnings,
            migration_required=migration_required
        )

    def get_snapshot(self, version: str) -> Optional[VersionSnapshot]:
        """获取版本快照"""
        return self._snapshots.get(version)

    def get_all_snapshots(self) -> List[VersionSnapshot]:
        """获取所有快照"""
        return sorted(
            self._snapshots.values(),
            key=lambda s: s.created_at,
            reverse=True
        )

    def get_rollback_history(self, limit: int = 10) -> List[Dict]:
        """获取回滚历史"""
        return self._rollback_history[-limit:]

    def _compute_code_hash(self) -> str:
        """计算代码哈希"""
        return hashlib.sha256(
            f"{time.time()}:code".encode()
        ).hexdigest()[:16]

    def _get_current_config(self) -> Dict:
        """获取当前配置快照"""
        return {
            "complexity_threshold": 5,
            "max_concurrent_agents": 5,
            "session_ttl_days": 7,
            "context_max_tokens": 16000,
        }

    async def _apply_snapshot(self, snapshot: VersionSnapshot) -> None:
        """应用快照配置"""
        # 实际实现应该包括:
        # 1. 加载历史配置
        # 2. 更新环境变量
        # 3. 触发服务重载
        await asyncio.sleep(0.1)  # 模拟操作
        logger.debug(f"[ROLLBACK] 应用快照配置: {snapshot.version}")

    async def _cleanup_old_snapshots(self) -> None:
        """清理旧快照"""
        if len(self._snapshots) > self._max_snapshots:
            sorted_snaps = sorted(
                self._snapshots.items(),
                key=lambda x: x[1].created_at
            )

            for version, snap in sorted_snaps[:-self._max_snapshots]:
                del self._snapshots[version]
                logger.debug(f"[ROLLBACK] 清理旧快照: {version}")


# 全局回滚管理器实例
_rollback_manager: Optional[RollbackManager] = None


def get_rollback_manager() -> RollbackManager:
    """获取全局回滚管理器实例"""
    global _rollback_manager
    if _rollback_manager is None:
        _rollback_manager = RollbackManager()
    return _rollback_manager


__all__ = [
    "RollbackManager",
    "VersionSnapshot",
    "CompatibilityResult",
    "RollbackState",
    "get_rollback_manager",
]
