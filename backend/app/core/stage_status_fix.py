"""QueryEngine 阶段状态发送修复

确保所有 8 个阶段都正确发送 start 和 complete 状态到前端。
"""

import logging
from typing import Callable, Awaitable, Any
from enum import Enum

logger = logging.getLogger(__name__)


class StageStatus(Enum):
    """阶段状态"""
    START = "start"
    COMPLETE = "complete"
    SKIP = "skip"
    ERROR = "error"


async def execute_with_stage_tracking(
    stage_name: str,
    emit_stage_func: Callable[[Any, str], Awaitable[None]],
    stage_enum: Any,
    execute_func: Callable[[], Awaitable[Any]]
) -> Any:
    """执行阶段并自动发送 start 和 complete 状态

    Args:
        stage_name: 阶段名称（用于日志）
        emit_stage_func: _emit_stage 函数
        stage_enum: WorkflowStage 枚举值
        execute_func: 要执行的异步函数

    Returns:
        execute_func 的执行结果
    """
    try:
        # 发送开始状态
        await emit_stage_func(stage_enum, StageStatus.START.value)
        logger.debug(f"[StageTracking] ✅ {stage_name} - start 已发送")

        # 执行阶段逻辑
        result = await execute_func()

        # 发送完成状态
        await emit_stage_func(stage_enum, StageStatus.COMPLETE.value)
        logger.debug(f"[StageTracking] ✅ {stage_name} - complete 已发送")

        return result

    except Exception as e:
        # 发送错误状态
        await emit_stage_func(stage_enum, StageStatus.ERROR.value)
        logger.error(f"[StageTracking] ❌ {stage_name} - 执行失败: {e}")
        raise


def create_stage_fix_patch():
    """创建阶段修复补丁

    为 QueryEngine._process_streaming_attempt 添加阶段完成状态发送
    """

    patch_code = """
# 在每个阶段完成后添加状态发送

# STAGE_1_INTENT 完成后（line 1874）
await _emit_stage(WorkflowStage.STAGE_1_INTENT, "complete")

# STAGE_2_STORAGE 完成后（line 1956）
await _emit_stage(WorkflowStage.STAGE_2_STORAGE, "complete")

# STAGE_3_CTX_CLEAN 完成后（line 1992）
await _emit_stage(WorkflowStage.STAGE_3_CTX_CLEAN, "complete")

# STAGE_4_TOOLS 完成后（line 2079）
await _emit_stage(WorkflowStage.STAGE_4_TOOLS, "complete")

# STAGE_5_CONTEXT 完成后（line 2095）
await _emit_stage(WorkflowStage.STAGE_5_CONTEXT, "complete")

# STAGE_6_LLM 完成后（line 2123）
await _emit_stage(WorkflowStage.STAGE_6_LLM, "complete")

# STAGE_7_CTX_MANAGE 完成后（line 2139）
await _emit_stage(WorkflowStage.STAGE_7_CTX_MANAGE, "complete")

# STAGE_8_MEMORY 完成后（line 2153）
await _emit_stage(WorkflowStage.STAGE_8_MEMORY, "complete")
"""

    return patch_code


def get_stage_fix_locations():
    """获取需要添加完成状态的代码位置

    Returns:
        List of (line_number, stage_name, stage_enum) tuples
    """
    return [
        (1874, "STAGE_1_INTENT", "WorkflowStage.STAGE_1_INTENT"),
        (1956, "STAGE_2_STORAGE", "WorkflowStage.STAGE_2_STORAGE"),
        (1992, "STAGE_3_CTX_CLEAN", "WorkflowStage.STAGE_3_CTX_CLEAN"),
        (2079, "STAGE_4_TOOLS", "WorkflowStage.STAGE_4_TOOLS"),
        (2095, "STAGE_5_CONTEXT", "WorkflowStage.STAGE_5_CONTEXT"),
        (2123, "STAGE_6_LLM", "WorkflowStage.STAGE_6_LLM"),
        (2139, "STAGE_7_CTX_MANAGE", "WorkflowStage.STAGE_7_CTX_MANAGE"),
        (2153, "STAGE_8_MEMORY", "WorkflowStage.STAGE_8_MEMORY"),
    ]


__all__ = [
    "StageStatus",
    "execute_with_stage_tracking",
    "create_stage_fix_patch",
    "get_stage_fix_locations",
]
