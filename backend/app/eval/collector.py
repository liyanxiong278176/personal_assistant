"""评估数据收集器 — QueryEngine 工作流中的数据钩子

设计原则:
1. 所有 record_* 方法同步，立即返回（不阻塞工作流）
2. 实际存储通过 create_task 后台执行
3. 任何异常被捕获，不影响 QueryEngine 主流程
4. 同一条 trace 只保存一次（幂等保护）
"""
import asyncio
import logging
from typing import Dict, Set, Any

logger = logging.getLogger(__name__)


class EvaluationCollector:
    """评估数据收集器 — 零侵入集成到 QueryEngine"""

    def __init__(self, storage: Any):
        """
        Args:
            storage: EvalStorage 实例
        """
        self.storage = storage
        self._current_trajectories: Dict[str, Any] = {}
        self._save_locks: Dict[str, asyncio.Lock] = {}
        self._saved_trace_ids: Set[str] = set()

    # === 同步钩子方法（立即返回）===

    def start_trajectory(self, trace_id: str, user_message: str, **kwargs) -> str:
        """启动轨迹 — 在意图识别后立即调用

        Args:
            trace_id: 轨迹ID（必填）
            user_message: 用户消息（必填）
            **kwargs: 其他字段，支持 conversation_id, user_id 等
        """
        try:
            from .models import TrajectoryModel
            from datetime import datetime, timezone
            traj = TrajectoryModel(
                trace_id=trace_id,
                conversation_id=kwargs.get("conversation_id"),
                user_id=kwargs.get("user_id"),
                started_at=datetime.now(timezone.utc),
                user_message=user_message,
            )
            self._current_trajectories[trace_id] = traj
        except Exception as e:
            logger.exception(f"[Eval] start_trajectory failed: {e}")
        return trace_id

    def record_intent(self, trace_id: str, intent_result: Any) -> None:
        """记录意图 — 在意图分类后立即调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.intent_type = intent_result.intent
                traj.intent_confidence = intent_result.confidence
                traj.intent_method = getattr(intent_result, "method", "llm")
        except Exception as e:
            logger.exception(f"[Eval] record_intent failed: {e}")

    def record_token_usage(
        self,
        trace_id: str,
        tokens_before: int,
        tokens_after: int,
        **kwargs
    ) -> None:
        """记录 Token — 在上下文压缩后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.tokens_before_compress = tokens_before
                traj.tokens_after_compress = tokens_after
                traj.is_compressed = tokens_after < tokens_before
                for k, v in kwargs.items():
                    if hasattr(traj, k):
                        setattr(traj, k, v)
        except Exception as e:
            logger.exception(f"[Eval] record_token_usage failed: {e}")

    def record_tools_called(self, trace_id: str, tools: list) -> None:
        """记录工具调用 — 在工具执行后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.tools_called = tools
        except Exception as e:
            logger.exception(f"[Eval] record_tools_called failed: {e}")

    def record_verification(self, trace_id: str, verification_result: Any) -> None:
        """记录验证结果 — 在验证完成后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.verification_score = getattr(verification_result, "score", None)
                traj.verification_passed = getattr(verification_result, "passed", None)
                traj.iteration_count = getattr(verification_result, "iteration_number", 0)
        except Exception as e:
            logger.exception(f"[Eval] record_verification failed: {e}")

    # === 异步更新（流结束后）===

    async def update_trajectory_field(self, trace_id: str, **fields) -> None:
        """异步更新字段 — 在流式响应完全结束后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                for k, v in fields.items():
                    if hasattr(traj, k):
                        setattr(traj, k, v)
        except Exception as e:
            logger.exception(f"[Eval] update_trajectory_field failed: {e}")

    # === 异步保存（幂等）===

    async def save_trajectory_async(self, trace_id: str, success: bool = True) -> None:
        """异步保存轨迹 — 在工作流完成后调用（幂等，同一条只存一次）

        注意：为了确保数据被保存，这里使用同步等待而非 fire-and-forget。
        """
        try:
            # 幂等检查
            if trace_id in self._saved_trace_ids:
                return

            # 获取该 trace 专属锁
            if trace_id not in self._save_locks:
                self._save_locks[trace_id] = asyncio.Lock()

            async with self._save_locks[trace_id]:
                # 双重检查
                if trace_id in self._saved_trace_ids:
                    return

                traj = self._current_trajectories.pop(trace_id, None)
                if traj:
                    from datetime import datetime, timezone
                    traj.completed_at = datetime.now(timezone.utc)
                    traj.success = success
                    # 同步等待保存完成，确保 HTTP 请求返回前数据已保存
                    await self.storage.save_trajectory(traj)
                self._saved_trace_ids.add(trace_id)
        except Exception as e:
            logger.exception(f"[Eval] save_trajectory_async failed: {e}")
