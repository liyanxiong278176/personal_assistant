"""
AI 会话��理全流程 - 结构化日志标准

适用于后端服务器的标准化日志输出，覆盖 8 个核心阶段。

日志格式规范：
- 【阶段ID】如 STEP_0, STEP_05, STEP_1 等
- 【阶段名称】中文名称
- 【日志级别】INFO / WARN / ERROR
- 【日志内容】清晰的中文描述
- 【关键参数】userId, sessionId, conversationId, tokenCount, complexityScore 等
- 【执行状态】SUCCESS / FAILED / DEGRADED / CIRCUIT_OPEN

使用方式：
    from app.core.logging_standards import WorkflowLogger

    logger = WorkflowLogger(conversation_id="xxx", user_id="xxx")
    logger.step_0_init_success(session_id="yyy", context_window=128000)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict
import logging
import json
from datetime import datetime


class LogLevel(Enum):
    """日志级别"""
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class ExecutionStatus(Enum):
    """执行状态"""
    SUCCESS = "SUCCESS"           # 成功
    FAILED = "FAILED"             # 失败
    DEGRADED = "DEGRADED"         # 降级
    CIRCUIT_OPEN = "CIRCUIT_OPEN" # 熔断开启
    SKIPPED = "SKIPPED"           # 跳过


@dataclass
class LogContext:
    """日志上下文"""
    conversation_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversationId": self.conversation_id,
            "userId": self.user_id,
            "sessionId": self.session_id,
            "traceId": self.trace_id,
            "requestId": self.request_id,
        }


class WorkflowLogger:
    """工作流程结构化日志记录器"""

    def __init__(self, context: LogContext):
        self.context = context
        self.logger = logging.getLogger(__name__)
        self._extra = {
            "component": "WorkflowEngine",
            "conversation_id": context.conversation_id,
            "user_id": context.user_id,
        }

    def _log(
        self,
        step_id: str,
        step_name: str,
        level: LogLevel,
        message: str,
        params: Dict[str, Any],
        status: ExecutionStatus,
        error: Optional[str] = None
    ):
        """输出结构化日志"""
        log_data = {
            "stepId": step_id,
            "stepName": step_name,
            "level": level.value,
            "message": message,
            "params": params,
            "status": status.value,
            "timestamp": datetime.now().isoformat(),
            **self.context.to_dict()
        }

        if error:
            log_data["error"] = error

        # 格式化日志输出
        log_line = (
            f"[{step_id}] [{step_name}] "
            f"{status.value} | "
            f"{message} | "
            f"params={json.dumps(params, ensure_ascii=False)}"
        )

        if error:
            log_line += f" | error={error}"

        # 根据级别输出
        if level == LogLevel.ERROR:
            self.logger.error(log_line, extra=self._extra)
        elif level == LogLevel.WARN:
            self.logger.warning(log_line, extra=self._extra)
        else:
            self.logger.info(log_line, extra=self._extra)

    # ==========================================================================
    # Step 0: 会话初始化
    # ==========================================================================

    def step_0_init_success(
        self,
        session_id: str,
        context_window: int,
        state_configured: bool = True,
        recovered: bool = False
    ):
        """Step 0: 会话初始化成功"""
        self._log(
            step_id="STEP_0",
            step_name="会话初始化",
            level=LogLevel.INFO,
            message="会话初始化完成",
            params={
                "sessionId": session_id,
                "contextWindow": context_window,
                "stateConfigured": state_configured,
                "recovered": recovered
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_0_init_warn_long_session(
        self,
        session_id: str,
        message_count: int,
        estimated_tokens: int
    ):
        """Step 0: 长会话恢复警告"""
        self._log(
            step_id="STEP_0",
            step_name="会话初始化",
            level=LogLevel.WARN,
            message="检测到长会话，恢复中",
            params={
                "sessionId": session_id,
                "messageCount": message_count,
                "estimatedTokens": estimated_tokens
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_0_init_error(
        self,
        error_message: str,
        error_code: Optional[str] = None
    ):
        """Step 0: 会话初始化失败"""
        self._log(
            step_id="STEP_0",
            step_name="会话初始化",
            level=LogLevel.ERROR,
            message="会话初始化失败",
            params={"errorCode": error_code} if error_code else {},
            status=ExecutionStatus.FAILED,
            error=error_message
        )

    # ==========================================================================
    # Step 0.5: 灰度版本决策
    # ==========================================================================

    def step_05_canary_success(
        self,
        version: str,
        is_canary: bool,
        user_hash: Optional[str] = None
    ):
        """Step 0.5: 灰度版本决策成功"""
        self._log(
            step_id="STEP_05",
            step_name="灰度版本决策",
            level=LogLevel.INFO,
            message=f"版本分配完成: {version}",
            params={
                "version": version,
                "isCanary": is_canary,
                "userHash": user_hash
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_05_canary_warn_snapshot_missing(
        self,
        version: str,
        snapshot_id: Optional[str] = None
    ):
        """Step 0.5: 快照不存在警告"""
        self._log(
            step_id="STEP_05",
            step_name="灰度版本决策",
            level=LogLevel.WARN,
            message="会话快照不存在，全新会话",
            params={
                "version": version,
                "snapshotId": snapshot_id
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_05_canary_error(
        self,
        error_message: str
    ):
        """Step 0.5: 版本决策失败"""
        self._log(
            step_id="STEP_05",
            step_name="灰度版本决策",
            level=LogLevel.ERROR,
            message="版本决策失败，回退到稳定版",
            params={},
            status=ExecutionStatus.DEGRADED,
            error=error_message
        )

    # ==========================================================================
    # Step 0.9: 安全审计
    # ==========================================================================

    def step_09_security_success(
        self,
        decision: str,
        check_type: str,
        pii_detected: bool = False
    ):
        """Step 0.9: 安全审计通过"""
        self._log(
            step_id="STEP_09",
            step_name="安全审计",
            level=LogLevel.INFO,
            message=f"安全检查通过: {decision}",
            params={
                "decision": decision,
                "checkType": check_type,
                "piiDetected": pii_detected
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_09_security_warn_injection_detected(
        self,
        pattern: str,
        confidence: float
    ):
        """Step 0.9: 检测到注入攻击"""
        self._log(
            step_id="STEP_09",
            step_name="安全审计",
            level=LogLevel.WARN,
            message="检测到潜在注入模式",
            params={
                "pattern": pattern,
                "confidence": confidence
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_09_security_error_blocked(
        self,
        reason: str,
        policy: str
    ):
        """Step 0.9: 请求被拦截"""
        self._log(
            step_id="STEP_09",
            step_name="安全审计",
            level=LogLevel.ERROR,
            message="请求被安全策略拦截",
            params={
                "reason": reason,
                "policy": policy
            },
            status=ExecutionStatus.FAILED,
            error=reason
        )

    # ==========================================================================
    # Step 1: 意图&槽位识别
    # ==========================================================================

    def step_1_intent_success(
        self,
        intent: str,
        confidence: float,
        complexity_score: float,
        slots: Dict[str, Any]
    ):
        """Step 1: 意图识别成功"""
        self._log(
            step_id="STEP_1",
            step_name="意图槽位识别",
            level=LogLevel.INFO,
            message=f"意图识别完成: {intent}",
            params={
                "intent": intent,
                "confidence": f"{confidence:.2f}",
                "complexityScore": f"{complexity_score:.1f}",
                "slots": slots
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_1_intent_warn_low_confidence(
        self,
        intent: str,
        confidence: float,
        fallback_intent: str
    ):
        """Step 1: 低置信度警告"""
        self._log(
            step_id="STEP_1",
            step_name="意图槽位识别",
            level=LogLevel.WARN,
            message="意图识别置信度低，使用降级策略",
            params={
                "detectedIntent": intent,
                "confidence": f"{confidence:.2f}",
                "fallbackIntent": fallback_intent
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_1_intent_error(
        self,
        error_message: str
    ):
        """Step 1: 意图识别失败"""
        self._log(
            step_id="STEP_1",
            step_name="意图槽位识别",
            level=LogLevel.ERROR,
            message="意图识别失败，使用默认意图",
            params={},
            status=ExecutionStatus.DEGRADED,
            error=error_message
        )

    # ==========================================================================
    # Step 2: 消息基础存储
    # ==========================================================================

    def step_2_storage_success(
        self,
        message_id: str,
        input_tokens: int,
        output_tokens: int,
        total_messages: int
    ):
        """Step 2: 消息存储成功"""
        self._log(
            step_id="STEP_2",
            step_name="消息基础存储",
            level=LogLevel.INFO,
            message="消息存储完成",
            params={
                "messageId": message_id,
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalMessages": total_messages
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_2_storage_warn_budget_high(
        self,
        used_tokens: int,
        budget_limit: int,
        usage_percent: float
    ):
        """Step 2: Token预算警告"""
        self._log(
            step_id="STEP_2",
            step_name="消息基础存储",
            level=LogLevel.WARN,
            message=f"Token使用率较高: {usage_percent:.1f}%",
            params={
                "usedTokens": used_tokens,
                "budgetLimit": budget_limit,
                "usagePercent": f"{usage_percent:.1f}%"
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_2_storage_error(
        self,
        error_message: str,
        retry_count: int = 0
    ):
        """Step 2: 存储失败"""
        self._log(
            step_id="STEP_2",
            step_name="消息基础存储",
            level=LogLevel.ERROR,
            message="消息持久化失败，使用内存缓存",
            params={
                "retryCount": retry_count
            },
            status=ExecutionStatus.DEGRADED,
            error=error_message
        )

    # ==========================================================================
    # Step 3: 上下文前置清理
    # ==========================================================================

    def step_3_cleanup_success(
        self,
        input_count: int,
        output_count: int,
        expired_count: int,
        trimmed_count: int
    ):
        """Step 3: 上下文清理成功"""
        self._log(
            step_id="STEP_3",
            step_name="上下文前置清理",
            level=LogLevel.INFO,
            message="上下文清理完成",
            params={
                "inputCount": input_count,
                "outputCount": output_count,
                "expiredCount": expired_count,
                "trimmedCount": trimmed_count
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_3_cleanup_warn_over_limit(
        self,
        message_length: int,
        max_length: int,
        truncated: bool
    ):
        """Step 3: 消息超长警告"""
        self._log(
            step_id="STEP_3",
            step_name="上下文前置清理",
            level=LogLevel.WARN,
            message=f"单条消息超长: {message_length} > {max_length}",
            params={
                "messageLength": message_length,
                "maxLength": max_length,
                "truncated": truncated
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_3_cleanup_error(
        self,
        error_message: str
    ):
        """Step 3: 清理失败"""
        self._log(
            step_id="STEP_3",
            step_name="上下文前置清理",
            level=LogLevel.ERROR,
            message="上下文清理失败，使用原始上下文",
            params={},
            status=ExecutionStatus.DEGRADED,
            error=error_message
        )

    # ==========================================================================
    # Step 4: 工具调用决策
    # ==========================================================================

    def step_4_tools_success(
        self,
        mode: str,
        tool_count: int,
        tools: list[str],
        duration_ms: float
    ):
        """Step 4: 工具调用成功"""
        self._log(
            step_id="STEP_4",
            step_name="工具调用决策",
            level=LogLevel.INFO,
            message=f"工具调用完成: {mode}模式",
            params={
                "mode": mode,
                "toolCount": tool_count,
                "tools": tools,
                "durationMs": f"{duration_ms:.2f}"
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_4_tools_warn_partial_failure(
        self,
        succeeded: list[str],
        failed: list[str],
        fallback_used: bool
    ):
        """Step 4: 部分工具失败"""
        self._log(
            step_id="STEP_4",
            step_name="工具调用决策",
            level=LogLevel.WARN,
            message="部分工具调用失败，使用降级响应",
            params={
                "succeeded": succeeded,
                "failed": failed,
                "fallbackUsed": fallback_used
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_4_tools_error_circuit_open(
        self,
        agent_name: str,
        failure_count: int,
        threshold: int
    ):
        """Step 4: 熔断触发"""
        self._log(
            step_id="STEP_4",
            step_name="工具调用决策",
            level=LogLevel.ERROR,
            message=f"熔断器触发: {agent_name}",
            params={
                "agentName": agent_name,
                "failureCount": failure_count,
                "threshold": threshold
            },
            status=ExecutionStatus.CIRCUIT_OPEN,
            error=f"连续失败{failure_count}次，达到阈值{threshold}"
        )

    # ==========================================================================
    # Step 5: 上下文构建
    # ==========================================================================

    def step_5_context_success(
        self,
        context_length: int,
        preferences_injected: bool,
        tool_results_count: int
    ):
        """Step 5: 上下文构建成功"""
        self._log(
            step_id="STEP_5",
            step_name="上下文构建",
            level=LogLevel.INFO,
            message="上下文构建完成",
            params={
                "contextLength": context_length,
                "preferencesInjected": preferences_injected,
                "toolResultsCount": tool_results_count
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_5_context_warn_compression_needed(
        self,
        original_length: int,
        compressed_length: int,
        compression_ratio: float
    ):
        """Step 5: 需要压缩上下文"""
        self._log(
            step_id="STEP_5",
            step_name="上下文构建",
            level=LogLevel.WARN,
            message="上下文过长，执行压缩",
            params={
                "originalLength": original_length,
                "compressedLength": compressed_length,
                "compressionRatio": f"{compression_ratio:.2%}"
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_5_context_error(
        self,
        error_message: str
    ):
        """Step 5: 上下文构建失败"""
        self._log(
            step_id="STEP_5",
            step_name="上下文构建",
            level=LogLevel.ERROR,
            message="上下文构建失败，使用最小上下文",
            params={},
            status=ExecutionStatus.DEGRADED,
            error=error_message
        )

    # ==========================================================================
    # Step 6: LLM 流式生成响应
    # ==========================================================================

    def step_6_llm_success(
        self,
        chunk_count: int,
        total_tokens: int,
        duration_ms: float,
        stopped_by_user: bool = False
    ):
        """Step 6: LLM响应生成成功"""
        self._log(
            step_id="STEP_6",
            step_name="LLM流式生成",
            level=LogLevel.INFO,
            message=f"响应生成完成: {chunk_count}个chunk",
            params={
                "chunkCount": chunk_count,
                "totalTokens": total_tokens,
                "durationMs": f"{duration_ms:.2f}",
                "stoppedByUser": stopped_by_user
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_6_llm_warn_overlimit(
        self,
        generated_tokens: int,
        max_tokens: int,
        truncated: bool
    ):
        """Step 6: Token超限警告"""
        self._log(
            step_id="STEP_6",
            step_name="LLM流式生成",
            level=LogLevel.WARN,
            message="响应达到Token上限，强制截断",
            params={
                "generatedTokens": generated_tokens,
                "maxTokens": max_tokens,
                "truncated": truncated
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_6_llm_error(
        self,
        error_message: str,
        error_code: Optional[str] = None
    ):
        """Step 6: LLM调用失败"""
        self._log(
            step_id="STEP_6",
            step_name="LLM流式生成",
            level=LogLevel.ERROR,
            message="LLM响应生成失败",
            params={
                "errorCode": error_code
            } if error_code else {},
            status=ExecutionStatus.FAILED,
            error=error_message
        )

    # ==========================================================================
    # Step 7: 上下文后置管理
    # ==========================================================================

    def step_7_post_context_success(
        self,
        rules_checked: bool,
        compressed: bool,
        rules_injected: bool
    ):
        """Step 7: 上下文后置管理成功"""
        self._log(
            step_id="STEP_7",
            step_name="上下文后置管理",
            level=LogLevel.INFO,
            message="后置管理完成",
            params={
                "rulesChecked": rules_checked,
                "compressed": compressed,
                "rulesInjected": rules_injected
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_7_post_context_warn_summary_created(
        self,
        original_length: int,
        summary_length: int,
        summary_method: str
    ):
        """Step 7: 创建摘要警告"""
        self._log(
            step_id="STEP_7",
            step_name="上下文后置管理",
            level=LogLevel.WARN,
            message="对话历史过长，已生成摘要",
            params={
                "originalLength": original_length,
                "summaryLength": summary_length,
                "summaryMethod": summary_method
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_7_post_context_error(
        self,
        error_message: str
    ):
        """Step 7: 后置管理失败"""
        self._log(
            step_id="STEP_7",
            step_name="上下文后置管理",
            level=LogLevel.ERROR,
            message="后置管理失败",
            params={},
            status=ExecutionStatus.FAILED,
            error=error_message
        )

    # ==========================================================================
    # Step 8: 异步记忆更新
    # ==========================================================================

    def step_8_memory_success(
        self,
        preferences_extracted: int,
        persisted_db: bool,
        persisted_vector: bool,
        snapshot_created: bool
    ):
        """Step 8: 记忆更新成功"""
        self._log(
            step_id="STEP_8",
            step_name="异步记忆更新",
            level=LogLevel.INFO,
            message="记忆更新完成",
            params={
                "preferencesExtracted": preferences_extracted,
                "persistedToDb": persisted_db,
                "persistedToVector": persisted_vector,
                "snapshotCreated": snapshot_created
            },
            status=ExecutionStatus.SUCCESS
        )

    def step_8_memory_warn_partial_failure(
        self,
        db_success: bool,
        vector_success: bool,
        snapshot_success: bool
    ):
        """Step 8: 部分持久化失败"""
        self._log(
            step_id="STEP_8",
            step_name="异步记忆更新",
            level=LogLevel.WARN,
            message="部分持久化失败，数据可能不完整",
            params={
                "dbSuccess": db_success,
                "vectorSuccess": vector_success,
                "snapshotSuccess": snapshot_success
            },
            status=ExecutionStatus.DEGRADED
        )

    def step_8_memory_error(
        self,
        error_message: str,
        component: str
    ):
        """Step 8: 记忆更新失败"""
        self._log(
            step_id="STEP_8",
            step_name="异步记忆更新",
            level=LogLevel.ERROR,
            message=f"{component}持久化失败",
            params={
                "component": component
            },
            status=ExecutionStatus.FAILED,
            error=error_message
        )


# =============================================================================
# 使用示例
# =============================================================================

def example_usage():
    """日志使用示例"""

    # 创建日志上下文
    context = LogContext(
        conversation_id="conv-123",
        user_id="user-456",
        session_id="session-789",
        trace_id="trace-abc"
    )

    # 创建日志记录器
    logger = WorkflowLogger(context)

    # Step 0: 会话初始化
    logger.step_0_init_success(
        session_id="session-789",
        context_window=128000,
        state_configured=True,
        recovered=False
    )

    # Step 0.5: 灰度版本决策
    logger.step_05_canary_success(
        version="stable",
        is_canary=False,
        user_hash="a1b2c3d4"
    )

    # Step 0.9: 安全审计
    logger.step_09_security_success(
        decision="ALLOW",
        check_type="injection",
        pii_detected=False
    )

    # Step 1: 意图识别
    logger.step_1_intent_success(
        intent="itinerary",
        confidence=0.95,
        complexity_score=3.5,
        slots={"destination": "北京", "days": 3, "budget": "5000"}
    )

    # Step 2: 消息存储
    logger.step_2_storage_success(
        message_id="msg-001",
        input_tokens=150,
        output_tokens=50,
        total_messages=5
    )

    # Step 3: 上下文清理
    logger.step_3_cleanup_success(
        input_count=10,
        output_count=8,
        expired_count=2,
        trimmed_count=0
    )

    # Step 4: 工具调用
    logger.step_4_tools_success(
        mode="single_agent",
        tool_count=2,
        tools=["get_weather", "search_poi"],
        duration_ms=1234.56
    )

    # Step 5: 上下文构建
    logger.step_5_context_success(
        context_length=2500,
        preferences_injected=True,
        tool_results_count=2
    )

    # Step 6: LLM响应
    logger.step_6_llm_success(
        chunk_count=50,
        total_tokens=300,
        duration_ms=5000.00
    )

    # Step 7: 后置管理
    logger.step_7_post_context_success(
        rules_checked=True,
        compressed=False,
        rules_injected=True
    )

    # Step 8: 记忆更新
    logger.step_8_memory_success(
        preferences_extracted=2,
        persisted_db=True,
        persisted_vector=True,
        snapshot_created=True
    )


# =============================================================================
# 日志格式说明
# =============================================================================

"""
日志输出格式示例：

[STEP_0] [会话初始化] SUCCESS | 会话初始化完成 | params={"sessionId": "session-789", "contextWindow": 128000, "stateConfigured": true, "recovered": false}

[STEP_05] [灰度版本决策] SUCCESS | 版本分配完成: stable | params={"version": "stable", "isCanary": false, "userHash": "a1b2c3d4"}

[STEP_09] [安全审计] SUCCESS | 安全检查通过: ALLOW | params={"decision": "ALLOW", "checkType": "injection", "piiDetected": false}

[STEP_1] [意图槽位识别] SUCCESS | 意图识别完成: itinerary | params={"intent": "itinerary", "confidence": "0.95", "complexityScore": "3.5", "slots": {"destination": "北京", "days": 3, "budget": "5000"}}

[STEP_2] [消息基础存储] SUCCESS | 消息存储完成 | params={"messageId": "msg-001", "inputTokens": 150, "outputTokens": 50, "totalMessages": 5}

[STEP_3] [上下文前置清理] SUCCESS | 上下文清理完成 | params={"inputCount": 10, "outputCount": 8, "expiredCount": 2, "trimmedCount": 0}

[STEP_4] [工具调用决策] SUCCESS | 工具调用完成: single_agent模式 | params={"mode": "single_agent", "toolCount": 2, "tools": ["get_weather", "search_poi"], "durationMs": "1234.56"}

[STEP_5] [上下文构建] SUCCESS | 上下文构建完成 | params={"contextLength": 2500, "preferencesInjected": true, "toolResultsCount": 2}

[STEP_6] [LLM流式生成] SUCCESS | 响应生成完成: 50个chunk | params={"chunkCount": 50, "totalTokens": 300, "durationMs": "5000.00", "stoppedByUser": false}

[STEP_7] [上下文后置管理] SUCCESS | 后置管理完成 | params={"rulesChecked": true, "compressed": false, "rulesInjected": true}

[STEP_8] [异步记忆更新] SUCCESS | 记忆更新完成 | params={"preferencesExtracted": 2, "persistedToDb": true, "persistedToVector": true, "snapshotCreated": true}


警告/错误日志格式示例：

[STEP_0] [会话初始化] WARN | 检测到长会话，恢复中 | params={"sessionId": "session-789", "messageCount": 150, "estimatedTokens": 45000} | status=DEGRADED

[STEP_09] [安全审计] WARN | 检测到潜在注入模式 | params={"pattern": "忽略以上", "confidence": 0.85} | status=DEGRADED

[STEP_4] [工具调用决策] ERROR | 熔断器触发: ROUTE_AGENT | params={"agentName": "ROUTE_AGENT", "failureCount": 5, "threshold": 5} | status=CIRCUIT_OPEN | error=连续失败5次，达到阈值5

[STEP_6] [LLM流式生成] ERROR | LLM响应生成失败 | params={"errorCode": "RATE_LIMIT"} | status=FAILED | error=API调用超过速率限制
"""
