"""结果气泡 - 收集子Agent结果并冒泡���父上下文"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from dataclasses import dataclass, field

from .session import SubAgentSession, SubAgentStatus
from .result import AgentResult, AgentType

logger = logging.getLogger(__name__)


@dataclass
class BubbleStats:
    """气泡统计信息"""
    total: int = 0
    successful: int = 0
    failed: int = 0
    timeout: int = 0
    total_execution_time: float = 0.0
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "timeout": self.timeout,
            "total_execution_time": round(self.total_execution_time, 3),
            "results": self.results,
            "errors": self.errors,
        }


class ResultBubble:
    """结果气泡

    职责：
    1. 收集所有子Agent的执行结果
    2. 按Agent类型组织结果
    3. 统计执行情况
    4. 将结果合并到父上下文

    "冒泡"隐喻：子Agent的结果���气泡一样向上浮动，
    最终合并到父Agent的上下文中。
    """

    def __init__(self, parent_session_id: Optional[UUID] = None):
        """初始化结果气泡

        Args:
            parent_session_id: 父会话ID
        """
        self.parent_session_id = parent_session_id
        self._sessions: List[SubAgentSession] = []

        logger.debug(
            f"[BUBBLE] 🫧 初始化 | "
            f"parent={parent_session_id}"
        )

    async def bubble_up(
        self,
        sessions: List[SubAgentSession],
        parent_context: Optional[Dict[str, Any]] = None
    ) -> BubbleStats:
        """收集子Agent结果并冒泡

        Args:
            sessions: 子Agent会话列表
            parent_context: 父上下文（可选，用于合并）

        Returns:
            气泡统计信息
        """
        self._sessions = sessions
        stats = BubbleStats()

        logger.info(
            f"[BUBBLE] 🫧 开始收集结果 | "
            f"parent={self.parent_session_id} | "
            f"子Agent数={len(sessions)}"
        )

        for session in sessions:
            stats.total += 1

            logger.debug(
                f"[BUBBLE] 📊 处理会话 | "
                f"type={session.agent_type.value} | "
                f"status={session.status.value} | "
                f"exec_time={session.execution_time}"
            )

            # 统计状态
            if session.status == SubAgentStatus.COMPLETED:
                stats.successful += 1
            elif session.status == SubAgentStatus.FAILED:
                stats.failed += 1
            elif session.status == SubAgentStatus.TIMEOUT:
                stats.timeout += 1

            # 收集执行时间
            if session.execution_time:
                stats.total_execution_time += session.execution_time

            # 收集结果
            if session.result:
                agent_key = session.agent_type.value

                # 如果结果是 AgentResult，提取数据
                if isinstance(session.result, AgentResult):
                    if session.result.success:
                        stats.results[agent_key] = session.result.data
                        logger.debug(
                            f"[BUBBLE] ✅ 收集成功结果 | "
                            f"agent={agent_key} | "
                            f"keys={list(session.result.data.keys()) if isinstance(session.result.data, dict) else 'N/A'}"
                        )
                    else:
                        stats.errors.append(
                            f"{agent_key}: {session.result.error}"
                        )
                        logger.warning(
                            f"[BUBBLE] ⚠️ 收集失败结果 | "
                            f"agent={agent_key} | "
                            f"error={session.result.error}"
                        )
                elif isinstance(session.result, dict):
                    stats.results[agent_key] = session.result
                    logger.debug(
                        f"[BUBBLE] ✅ 收集字典结果 | "
                        f"agent={agent_key} | "
                        f"keys={list(session.result.keys())}"
                    )
                else:
                    stats.results[agent_key] = {"data": session.result}

            # 收集错误
            if session.error:
                error_msg = f"{session.agent_type.value}: {str(session.error)}"
                stats.errors.append(error_msg)
                logger.error(
                    f"[BUBBLE] ❌ 会话错误 | "
                    f"agent={session.agent_type.value} | "
                    f"error={str(session.error)}"
                )

        # 合并到父上下文
        if parent_context is not None:
            logger.debug(
                f"[BUBBLE] 🔗 合并到父上下文 | "
                f"结果数={len(stats.results)} | "
                f"父上下文原有键={list(parent_context.keys())}"
            )
            self._merge_to_parent(stats.results, parent_context)

        logger.info(
            f"[BUBBLE] ✅ 结果收集完成 | "
            f"总计={stats.total} | "
            f"成功={stats.successful} | "
            f"失败={stats.failed} | "
            f"超时={stats.timeout} | "
            f"耗时={stats.total_execution_time:.3f}s | "
            f"结果键={list(stats.results.keys())}"
        )

        return stats

    def _merge_to_parent(
        self,
        results: Dict[str, Any],
        parent_context: Dict[str, Any]
    ) -> None:
        """将结果合并到父上下文

        Args:
            results: 子Agent结果
            parent_context: 父上下文（会被修改）
        """
        # 直接合并所有结果
        parent_context.update(results)

        # 特殊处理：合并路线信息
        if "route" in results and "hotels" in results:
            # 将酒店信息附加到路线结果中
            if isinstance(results["route"], dict):
                results["route"]["hotels"] = results["hotels"]

    def get_failed_sessions(self) -> List[SubAgentSession]:
        """获取失败的会话

        Returns:
            失败的会话列表
        """
        failed = [
            s for s in self._sessions
            if s.status in (SubAgentStatus.FAILED, SubAgentStatus.TIMEOUT)
        ]

        if failed:
            logger.warning(
                f"[BUBBLE] ⚠️ 获取失败会话 | "
                f"数量={len(failed)} | "
                f"types={[s.agent_type.value for s in failed]}"
            )

        return failed

    def get_successful_results(self) -> Dict[str, Any]:
        """获取成功的结果

        Returns:
            Agent类型 -> 结果的映射
        """
        results = {}
        for session in self._sessions:
            if session.status == SubAgentStatus.COMPLETED and session.result:
                agent_key = session.agent_type.value
                if isinstance(session.result, AgentResult):
                    if session.result.success:
                        results[agent_key] = session.result.data
                elif isinstance(session.result, dict):
                    results[agent_key] = session.result
                else:
                    results[agent_key] = {"data": session.result}

        logger.debug(
            f"[BUBBLE] 📤 获取成功结果 | "
            f"数量={len(results)} | "
            f"types={list(results.keys())}"
        )

        return results

    def format_for_llm(self, stats: BubbleStats) -> str:
        """格式化结果供LLM使用

        Args:
            stats: 气泡统计信息

        Returns:
            格式化的字符串
        """
        lines = [
            "# 子Agent执行结果",
            f"- 总计: {stats.total} 个Agent",
            f"- 成功: {stats.successful} 个",
            f"- 失败: {stats.failed} 个",
            f"- 超时: {stats.timeout} 个",
            f"- 总耗时: {stats.total_execution_time:.2f}秒",
            "",
            "## 详细结果"
        ]

        for agent_type, result in stats.results.items():
            lines.append(f"\n### {agent_type}")
            if isinstance(result, dict):
                for key, value in result.items():
                    lines.append(f"- {key}: {value}")
            else:
                lines.append(f"- {result}")

        if stats.errors:
            lines.append("\n## 错误信息")
            for error in stats.errors:
                lines.append(f"- {error}")

        formatted = "\n".join(lines)
        logger.debug(
            f"[BUBBLE] 📝 格式化完成 | "
            f"长度={len(formatted)}字符"
        )

        return formatted

    async def bubble_up_with_format(
        self,
        sessions: List[SubAgentSession],
        parent_context: Optional[Dict[str, Any]] = None
    ) -> tuple[BubbleStats, str]:
        """收集结果并返回LLM格式化字符串

        Args:
            sessions: 子Agent会话列表
            parent_context: 父上下文（可选）

        Returns:
            (统计信息, 格式化字符串)
        """
        stats = await self.bubble_up(sessions, parent_context)
        formatted = self.format_for_llm(stats)
        return stats, formatted
