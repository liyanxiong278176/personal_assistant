"""Token预算管理器

防止单用户Token消耗超限，导致API成本超支。

功能:
1. 会话级Token预算追踪
2. 预算超限时的强制压缩
3. 多会话Token统计
4. 预算告警机制
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class BudgetAction(Enum):
    """预算动作"""
    ALLOW = "allow"           # 允许
    WARN = "warn"             # 警告但允许
    COMPRESS = "compress"     # 强制压缩
    REJECT = "reject"         # 拒绝请求


@dataclass
class TokenBudget:
    """Token预算"""
    conversation_id: str
    total_budget: int          # 总预算
    used_tokens: int = 0       # 已使用
    last_updated: float = field(default_factory=time.time)
    warning_issued: bool = False
    compression_count: int = 0  # 压缩次数


@dataclass
class BudgetCheckResult:
    """预算检查结果"""
    action: BudgetAction
    allowed_tokens: int
    used_tokens: int
    remaining_tokens: int
    budget_percent: float
    message: str


class TokenBudgetManager:
    """Token预算管理器

    用法:
        manager = TokenBudgetManager()

        # 检查预算
        result = await manager.check_budget("conv-123", tokens=5000)
        if result.action == BudgetAction.COMPRESS:
            # 强制压缩上下文
            history = await manager.enforce_limit("conv-123", history)
        elif result.action == BudgetAction.REJECT:
            # 拒绝请求
            return "Token预算超限，请简化请求"

        # 记录使用
        await manager.record_usage("conv-123", tokens=5000)
    """

    def __init__(
        self,
        default_budget: int = 128000,
        warning_threshold: float = 0.8,
        critical_threshold: float = 0.95
    ):
        """
        Args:
            default_budget: 默认Token预算 (128K)
            warning_threshold: 警告阈值 (80%)
            critical_threshold: 临界阈值 (95%)
        """
        self._default_budget = default_budget
        self._warning_threshold = warning_threshold
        self._critical_threshold = critical_threshold
        self._budgets: Dict[str, TokenBudget] = {}
        self._total_usage: Dict[str, int] = {}  # 累计使用

        logger.info(
            f"[TOKEN_BUDGET] 初始化 | "
            f"default_budget={default_budget} | "
            f"warning={warning_threshold:.0%} | "
            f"critical={critical_threshold:.0%}"
        )

    async def check_budget(
        self,
        conversation_id: str,
        requested_tokens: int
    ) -> BudgetCheckResult:
        """检查Token预算

        Args:
            conversation_id: 会话ID
            requested_tokens: 请求的Token数量

        Returns:
            BudgetCheckResult: 检查结果
        """
        budget = self._get_or_create_budget(conversation_id)

        total_after = budget.used_tokens + requested_tokens
        budget_percent = total_after / budget.total_budget

        if budget_percent >= self._critical_threshold:
            # 临界阈值 - 拒绝或强制压缩
            action = BudgetAction.COMPRESS
            message = f"Token预算临界({budget_percent:.0%})，将强制压缩上下文"
            logger.warning(
                f"[TOKEN_BUDGET] 🚨 临界 | conv={conversation_id} | "
                f"used={budget.used_tokens} | request={requested_tokens} | "
                f"total={total_after}/{budget.total_budget}"
            )

        elif budget_percent >= self._warning_threshold:
            # 警告阈值 - 警告但允许
            if not budget.warning_issued:
                budget.warning_issued = True
                logger.warning(
                    f"[TOKEN_BUDGET] ⚠️ 警告 | conv={conversation_id} | "
                    f"预算使用{budget_percent:.0%}"
                )

            action = BudgetAction.WARN
            message = f"Token预算较高({budget_percent:.0%})，建议简化请求"

        else:
            action = BudgetAction.ALLOW
            message = f"Token预算充足({budget_percent:.0%})"

        return BudgetCheckResult(
            action=action,
            allowed_tokens=requested_tokens,
            used_tokens=budget.used_tokens,
            remaining_tokens=budget.total_budget - total_after,
            budget_percent=budget_percent,
            message=message
        )

    async def record_usage(
        self,
        conversation_id: str,
        tokens: int,
        is_input: bool = True
    ) -> None:
        """记录Token使用

        Args:
            conversation_id: 会话ID
            tokens: Token数量
            is_input: 是否为输入Token
        """
        budget = self._get_or_create_budget(conversation_id)
        budget.used_tokens += tokens
        budget.last_updated = time.time()

        # 累计使用
        key = f"{conversation_id}:input" if is_input else f"{conversation_id}:output"
        self._total_usage[key] = self._total_usage.get(key, 0) + tokens

        logger.debug(
            f"[TOKEN_BUDGET] 记录使用 | conv={conversation_id} | "
            f"tokens={tokens} | total={budget.used_tokens}/{budget.total_budget}"
        )

    async def enforce_limit(
        self,
        conversation_id: str,
        messages: List[Dict],
        target_tokens: Optional[int] = None
    ) -> List[Dict]:
        """强制执行上下文大小限制

        Args:
            conversation_id: 会话ID
            messages: 消息列表
            target_tokens: 目标Token数 (默认50%预算)

        Returns:
            压缩后的消息列表
        """
        budget = self._get_or_create_budget(conversation_id)
        target = target_tokens or int(budget.total_budget * 0.5)

        original_count = len(messages)
        original_tokens = sum(
            len(str(m.get("content", ""))) // 4 for m in messages
        )

        # 逐步删除最老的非关键消息
        while len(messages) > 5:
            current_tokens = sum(
                len(str(m.get("content", ""))) // 4 for m in messages
            )
            if current_tokens <= target:
                break

            # 跳过 system 消息
            if messages[0].get("role") == "system":
                messages = [messages[0]] + messages[2:]
            else:
                messages = messages[2:]

        budget.compression_count += 1
        budget.used_tokens = sum(
            len(str(m.get("content", ""))) // 4 for m in messages
        )

        logger.info(
            f"[TOKEN_BUDGET] 💪 强制压缩 | conv={conversation_id} | "
            f"messages={original_count}→{len(messages)} | "
            f"compressions={budget.compression_count}"
        )

        return messages

    def reset_budget(self, conversation_id: str) -> None:
        """重置会话预算"""
        if conversation_id in self._budgets:
            self._budgets[conversation_id].used_tokens = 0
            self._budgets[conversation_id].warning_issued = False
            logger.info(f"[TOKEN_BUDGET] 重置预算 | conv={conversation_id}")

    def get_budget_info(self, conversation_id: str) -> Optional[Dict]:
        """获取预算信息"""
        budget = self._budgets.get(conversation_id)
        if not budget:
            return None

        return {
            "conversation_id": budget.conversation_id,
            "total_budget": budget.total_budget,
            "used_tokens": budget.used_tokens,
            "remaining_tokens": budget.total_budget - budget.used_tokens,
            "usage_percent": budget.used_tokens / budget.total_budget,
            "compression_count": budget.compression_count,
            "last_updated": budget.last_updated,
        }

    def get_global_stats(self) -> Dict:
        """获取全局统计"""
        total_sessions = len(self._budgets)
        total_used = sum(b.used_tokens for b in self._budgets.values())
        total_budget = sum(b.total_budget for b in self._budgets.values())

        return {
            "active_sessions": total_sessions,
            "total_used_tokens": total_used,
            "total_budget_tokens": total_budget,
            "global_usage_percent": total_used / total_budget if total_budget > 0 else 0,
        }

    def _get_or_create_budget(self, conversation_id: str) -> TokenBudget:
        """获取或创建预算"""
        if conversation_id not in self._budgets:
            self._budgets[conversation_id] = TokenBudget(
                conversation_id=conversation_id,
                total_budget=self._default_budget
            )
        return self._budgets[conversation_id]


# 全局Token预算管理器
_token_budget_manager: Optional[TokenBudgetManager] = None


def get_token_budget_manager() -> TokenBudgetManager:
    """获取全局Token预算管理器"""
    global _token_budget_manager
    if _token_budget_manager is None:
        _token_budget_manager = TokenBudgetManager()
    return _token_budget_manager


__all__ = [
    "TokenBudgetManager",
    "TokenBudget",
    "BudgetAction",
    "BudgetCheckResult",
    "get_token_budget_manager",
]
