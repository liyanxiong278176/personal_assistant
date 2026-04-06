"""会话越权校验

UC4-1 修复: 防止用户越权访问其他用户的会话
"""

import logging
from typing import Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class AuthorizationError(Exception):
    """越权访问异常"""
    pass


class ConversationAuthorization:
    """会话权限管理器

    确保用户只能访问自己创建的会话，防止越权访问。
    """

    def __init__(self):
        # 会话 -> 用户ID 映射
        self._conversation_owners: Dict[str, str] = {}
        logger.info("[Auth] ConversationAuthorization initialized")

    def register_conversation(
        self,
        conversation_id: str,
        user_id: str
    ) -> None:
        """注册会话所有者

        Args:
            conversation_id: 会话ID
            user_id: 用户ID
        """
        self._conversation_owners[conversation_id] = user_id
        logger.debug(
            f"[Auth] 注册会话所有者 | "
            f"conv={conversation_id[:16]}... | user={user_id[:8]}..."
        )

    def validate_access(
        self,
        conversation_id: str,
        user_id: str
    ) -> bool:
        """验证用户是否有权访问会话

        Args:
            conversation_id: 会话ID
            user_id: 用户ID

        Returns:
            True 如果有权访问

        Raises:
            AuthorizationError 如果无权访问
        """
        # 如果会话未注册，允许访问（首次访问时注册）
        if conversation_id not in self._conversation_owners:
            logger.debug(
                f"[Auth] 会话未注册，自动注册 | "
                f"conv={conversation_id[:16]}... | user={user_id[:8]}..."
            )
            self.register_conversation(conversation_id, user_id)
            return True

        # 检查是否是会话所有者
        owner = self._conversation_owners[conversation_id]
        if owner != user_id:
            logger.warning(
                f"[Auth] 🚨 越权访问尝试 | "
                f"conv={conversation_id[:16]}... | "
                f"owner={owner[:8]}... | "
                f"requester={user_id[:8]}..."
            )
            raise AuthorizationError(
                f"用户 {user_id} 无权访问会话 {conversation_id}"
            )

        return True

    def is_owner(
        self,
        conversation_id: str,
        user_id: str
    ) -> bool:
        """检查用户是否是会话所有者"""
        return self._conversation_owners.get(conversation_id) == user_id

    def get_owner(self, conversation_id: str) -> Optional[str]:
        """获取会话所有者"""
        return self._conversation_owners.get(conversation_id)

    def revoke_access(
        self,
        conversation_id: str,
        user_id: str
    ) -> bool:
        """撤销用户对会话的访问权限"""
        if self.is_owner(conversation_id, user_id):
            del self._conversation_owners[conversation_id]
            logger.info(
                f"[Auth] 撤销会话访问权限 | "
                f"conv={conversation_id[:16]}... | user={user_id[:8]}..."
            )
            return True
        return False

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_conversations": len(self._conversation_owners),
            "unique_users": len(set(self._conversation_owners.values()))
        }


# 全局实例
_auth_manager: Optional[ConversationAuthorization] = None


def get_auth_manager() -> ConversationAuthorization:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = ConversationAuthorization()
    return _auth_manager


__all__ = [
    "AuthorizationError",
    "ConversationAuthorization",
    "get_auth_manager"
]
