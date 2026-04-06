"""会话快照

用于长会话的状态恢复和中断重连。

功能:
1. 会话状态快照
2. 增量状态保存
3. 快速状态恢复
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SnapshotType(Enum):
    """快照类型"""
    FULL = "full"           # 完整快照
    INCREMENTAL = "incremental"  # 增量快照
    COMPRESSED = "compressed"     # 压缩快照


@dataclass
class SessionSnapshot:
    """会话快照"""
    conversation_id: str
    snapshot_type: SnapshotType
    messages: List[Dict]
    preferences: Dict[str, Any]
    slots: Dict[str, Any]
    context_summary: str
    created_at: float = field(default_factory=time.time)
    version: int = 1
    expires_at: Optional[float] = None

    def __post_init__(self):
        if self.expires_at is None:
            # 默认24小时过期
            self.expires_at = time.time() + 86400

    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.expires_at

    def to_dict(self) -> Dict:
        return {
            "conversation_id": self.conversation_id,
            "snapshot_type": self.snapshot_type.value,
            "message_count": len(self.messages),
            "preferences": self.preferences,
            "slots": self.slots,
            "context_summary": self.context_summary,
            "created_at": self.created_at,
            "version": self.version,
            "expires_at": self.expires_at,
        }


class SessionSnapshotManager:
    """会话快照管理器

    用法:
        manager = SessionSnapshotManager()

        # 创建快照
        await manager.create_snapshot(
            conversation_id="conv-123",
            messages=history,
            preferences=user_prefs,
            slots=extracted_slots,
        )

        # 恢复快照
        snapshot = await manager.restore("conv-123")
        if snapshot:
            history = snapshot.messages
            prefs = snapshot.preferences

        # 清理过期快照
        await manager.cleanup_expired()
    """

    def __init__(
        self,
        max_snapshots_per_conversation: int = 5,
        snapshot_ttl_hours: int = 24
    ):
        self._snapshots: Dict[str, List[SessionSnapshot]] = {}
        self._max_per_conversation = max_snapshots_per_conversation
        self._ttl_seconds = snapshot_ttl_hours * 3600
        self._redis_client = None  # 可选：Redis存储

        logger.info(
            f"[SNAPSHOT] 初始化 | "
            f"max_per_conv={max_snapshots_per_conversation} | "
            f"ttl={snapshot_ttl_hours}h"
        )

    async def create_snapshot(
        self,
        conversation_id: str,
        messages: List[Dict],
        preferences: Optional[Dict[str, Any]] = None,
        slots: Optional[Dict[str, Any]] = None,
        snapshot_type: SnapshotType = SnapshotType.INCREMENTAL,
        context_summary: str = "",
    ) -> SessionSnapshot:
        """创建会话快照

        Args:
            conversation_id: 会话ID
            messages: 消息列表
            preferences: 用户偏好
            slots: 槽位信息
            snapshot_type: 快照类型
            context_summary: 上下文摘要

        Returns:
            SessionSnapshot: 快照对象
        """
        # 生成上下文摘要（如果未提供）
        if not context_summary and messages:
            recent_msgs = messages[-10:]
            context_summary = self._generate_summary(recent_msgs)

        snapshot = SessionSnapshot(
            conversation_id=conversation_id,
            snapshot_type=snapshot_type,
            messages=messages,
            preferences=preferences or {},
            slots=slots or {},
            context_summary=context_summary,
            version=len(self._snapshots.get(conversation_id, [])) + 1,
            expires_at=time.time() + self._ttl_seconds,
        )

        # 保存快照
        if conversation_id not in self._snapshots:
            self._snapshots[conversation_id] = []

        self._snapshots[conversation_id].append(snapshot)

        # 限制每个会话的快照数量
        if len(self._snapshots[conversation_id]) > self._max_per_conversation:
            self._snapshots[conversation_id] = self._snapshots[conversation_id][
                -self._max_per_conversation:
            ]

        logger.info(
            f"[SNAPSHOT] 创建快照 | "
            f"conv={conversation_id} | "
            f"type={snapshot_type.value} | "
            f"messages={len(messages)} | "
            f"version={snapshot.version}"
        )

        return snapshot

    async def restore(
        self,
        conversation_id: str
    ) -> Optional[SessionSnapshot]:
        """恢复最新快照

        Args:
            conversation_id: 会话ID

        Returns:
            Optional[SessionSnapshot]: 最新快照，不存在或过期返回None
        """
        snapshots = self._snapshots.get(conversation_id, [])

        # 过滤未过期的快照
        valid = [s for s in snapshots if not s.is_expired()]

        if not valid:
            logger.info(f"[SNAPSHOT] 无有效快照 | conv={conversation_id}")
            return None

        # 返回最新快照
        latest = valid[-1]
        logger.info(
            f"[SNAPSHOT] 恢复快照 | "
            f"conv={conversation_id} | "
            f"version={latest.version} | "
            f"messages={len(latest.messages)}"
        )

        return latest

    async def get_incremental(
        self,
        conversation_id: str,
        since_version: int
    ) -> Optional[List[Dict]]:
        """获取增量更新

        Args:
            conversation_id: 会话ID
            since_version: 从哪个版本开始

        Returns:
            增量消息列表
        """
        snapshots = self._snapshots.get(conversation_id, [])
        newer = [s for s in snapshots if s.version > since_version]

        if not newer:
            return None

        # 返回最新版本的完整消息（简化实现）
        return newer[-1].messages

    async def cleanup_expired(self) -> int:
        """清理过期快照

        Returns:
            清理的快照数量
        """
        cleaned = 0
        for conv_id in list(self._snapshots.keys()):
            before = len(self._snapshots[conv_id])
            self._snapshots[conv_id] = [
                s for s in self._snapshots[conv_id]
                if not s.is_expired()
            ]
            cleaned += before - len(self._snapshots[conv_id])

            if not self._snapshots[conv_id]:
                del self._snapshots[conv_id]

        if cleaned > 0:
            logger.info(f"[SNAPSHOT] 清理过期快照 {cleaned} 个")

        return cleaned

    def get_snapshot_info(
        self,
        conversation_id: str
    ) -> Optional[List[Dict]]:
        """获取快照信息列表"""
        snapshots = self._snapshots.get(conversation_id, [])
        return [s.to_dict() for s in snapshots]

    def _generate_summary(self, messages: List[Dict]) -> str:
        """生成上下文摘要"""
        if not messages:
            return ""

        roles = [m.get("role", "unknown") for m in messages]
        content_previews = [
            m.get("content", "")[:50]
            for m in messages[-5:]
        ]

        return f"轮次: {len(messages)}, 角色: {set(roles)}, 最新: {' | '.join(content_previews)}"


# 全局快照管理器
_snapshot_manager: Optional[SessionSnapshotManager] = None


def get_snapshot_manager() -> SessionSnapshotManager:
    """获取全局快照管理器"""
    global _snapshot_manager
    if _snapshot_manager is None:
        _snapshot_manager = SessionSnapshotManager()
    return _snapshot_manager


__all__ = [
    "SessionSnapshotManager",
    "SessionSnapshot",
    "SnapshotType",
    "get_snapshot_manager",
]
