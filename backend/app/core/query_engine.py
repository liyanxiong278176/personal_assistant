"""QueryEngine - Agent Core 总控

提供统一的查询处理入口，实现 6 步工作流程：
1. 意图 & 槽位识别
2. 消息基础存储
3. 按需并行调用工具
4. 上下文构建
5. LLM 生成响应
6. 异步记忆更新
"""

import asyncio
import json
import logging
import time
import traceback
from typing import AsyncIterator, Optional, List, Dict, Any, Union
from enum import Enum

from .llm import LLMClient, ToolCall
from .prompts import DEFAULT_SYSTEM_PROMPT
from .errors import AgentError, DegradationLevel
from .tools import ToolRegistry, global_registry
from .tools.executor import ToolExecutor
from .intent import IntentClassifier, SlotExtractor, intent_classifier

logger = logging.getLogger(__name__)


class WorkflowStage(Enum):
    """工作流程阶段枚举"""
    STAGE_0_INIT = "0_INIT"           # 初始化
    STAGE_1_INTENT = "1_INTENT"       # 意图识别
    STAGE_2_STORAGE = "2_STORAGE"      # 消息存储
    STAGE_3_TOOLS = "3_TOOLS"         # 工具执行
    STAGE_4_CONTEXT = "4_CONTEXT"     # 上下文构建
    STAGE_5_LLM = "5_LLM"             # LLM响应生成
    STAGE_6_MEMORY = "6_MEMORY"       # 记忆更新
    COMPLETE = "COMPLETE"             # 完成


class StageLogger:
    """阶段日志记录器"""

    def __init__(self, stage: WorkflowStage, conversation_id: str, user_id: Optional[str] = None):
        self.stage = stage
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.start_time: float = 0
        self.end_time: float = 0
        self.inputs: Dict[str, Any] = {}
        self.outputs: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def start(self, **kwargs):
        """开始阶段，记录输入"""
        self.start_time = time.perf_counter()
        self.inputs = kwargs
        logger.info(
            f"[WORKFLOW:{self.stage.value}] ⏳ 开始 | conv={self.conversation_id} | "
            f"输入: {self._format_inputs()}"
        )

    def end(self, **kwargs):
        """结束阶段，记录输出和耗时"""
        self.end_time = time.perf_counter()
        self.outputs = kwargs
        elapsed_ms = (self.end_time - self.start_time) * 1000

        if self.error:
            logger.error(
                f"[WORKFLOW:{self.stage.value}] ❌ 失败 | conv={self.conversation_id} | "
                f"耗时: {elapsed_ms:.2f}ms | 错误: {self.error}"
            )
        else:
            logger.info(
                f"[WORKFLOW:{self.stage.value}] ✅ 完成 | conv={self.conversation_id} | "
                f"耗时: {elapsed_ms:.2f}ms | 输出: {self._format_outputs()}"
            )

    def fail(self, error: str):
        """记录阶段失败"""
        self.error = error
        self.end()

    def _format_inputs(self) -> str:
        """格式化输入日志"""
        if not self.inputs:
            return "无"
        return json.dumps(self.inputs, ensure_ascii=False, indent=None)[:200]

    def _format_outputs(self) -> str:
        """格式化输出日志"""
        if not self.outputs:
            return "无"
        return json.dumps(self.outputs, ensure_ascii=False, indent=None)[:200]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.fail(f"{exc_type.__name__}: {exc_val}")
            logger.debug(f"[WORKFLOW:{self.stage.value}] 堆栈:\n{''.join(traceback.format_exception(exc_type, exc_val, exc_tb))}")
        return True  # 不阻止异常传播


def log_workflow_summary(
    conversation_id: str,
    intent: str,
    tool_calls: int,
    total_time_ms: float,
    response_length: int
):
    """记录工作流程总摘要"""
    logger.info(
        f"[WORKFLOW:SUMMARY] 📊 流程完成 | conv={conversation_id} | "
        f"意图={intent} | 工具调用={tool_calls}次 | "
        f"总耗时={total_time_ms:.2f}ms | 响应长度={response_length}字符"
    )


class QueryEngine:
    """QueryEngine - Agent Core 总控

    实现 6 步统一工作流程：
    1. 意图 & 槽位识别：使用三层分类器（缓存 -> 关键词 -> LLM）
    2. 消息基础存储：记录到工作记忆
    3. 按需并行调用工具：根据意图决定是否调用工具
    4. 上下文构建：整合工具结果、槽位、历史记录
    5. LLM 生成响应：基于完整上下文流式生成
    6. 异步记忆更新：后台任务更新持久化记忆
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None
    ):
        """Initialize QueryEngine.

        Args:
            llm_client: LLM 客户端实例，为 None 时创建默认实例
            system_prompt: 系统提示词，为 None 时使用默认值
            tool_registry: 工具注册表，为 None 时使用全局注册表
        """
        self.llm_client = llm_client
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._tool_registry = tool_registry or global_registry
        self._tool_executor = ToolExecutor(self._tool_registry)
        self._conversation_history: Dict[str, List[Dict[str, str]]] = {}

        # 意图分类器和槽位提取器
        self._intent_classifier = intent_classifier
        self._slot_extractor = SlotExtractor()

        logger.info(
            f"[QueryEngine] 🚀 初始化完成 | "
            f"工具数量={len(self._tool_registry.list_tools())} | "
            f"LLM客户端={'已配置' if llm_client else '未配置'}"
        )

        if self.llm_client is None:
            logger.warning("[QueryEngine] ⚠️ LLM客户端未配置，查询将失败")

    def set_llm_client(self, llm_client: LLMClient) -> None:
        """Set or update the LLM client.

        Args:
            llm_client: LLM client instance
        """
        self.llm_client = llm_client
        logger.info("[QueryEngine] 🔄 LLM客户端已更新")

    def set_tool_registry(self, tool_registry: ToolRegistry) -> None:
        """Set or update the tool registry.

        Args:
            tool_registry: Tool registry instance
        """
        self._tool_registry = tool_registry
        self._tool_executor = ToolExecutor(tool_registry)
        logger.info(f"[QueryEngine] 🔄 工具注册表已更新 | 工具数量={len(tool_registry.list_tools())}")

    def _get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """获取 LLM 可用的工具定义

        Returns:
            工具定义列表，格式符合 OpenAI Function Calling 规范
        """
        tools = []
        for tool in self._tool_registry.list_tools():
            meta = tool.metadata
            tools.append({
                "name": meta.name,
                "description": meta.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            })
        return tools

    async def _execute_tool_calls(
        self,
        tool_calls: List[ToolCall]
    ) -> Dict[str, Any]:
        """执行工具调用

        Args:
            tool_calls: 工具调用列表

        Returns:
            工具名称到执行结果的映射
        """
        results = {}

        for call in tool_calls:
            try:
                logger.info(f"[TOOL] 📤 执行工具: {call.name} | 参数: {call.arguments}")
                result = await self._tool_executor.execute(
                    call.name,
                    **call.arguments
                )
                results[call.name] = result
                logger.info(f"[TOOL] ✅ 工具完成: {call.name} | 结果长度: {len(str(result))}")
            except Exception as e:
                logger.error(f"[TOOL] ❌ 工具失败: {call.name} | 错误: {e}")
                results[call.name] = {"error": str(e)}

        return results

    def _format_tool_results_for_context(
        self,
        tool_results: Dict[str, Any]
    ) -> str:
        """将工具结果格式化为上下文字符串

        Args:
            tool_results: 工具执行结果

        Returns:
            格式化的上下文字符串
        """
        if not tool_results:
            return ""

        parts = ["\n\n[工具调用结果]"]
        for name, result in tool_results.items():
            parts.append(f"\n{name}:")
            if isinstance(result, dict) and "error" in result:
                parts.append(f"  错误: {result['error']}")
            else:
                try:
                    result_str = json.dumps(result, ensure_ascii=False, indent=2)
                    parts.append(f"  {result_str}")
                except Exception:
                    parts.append(f"  {result}")
        parts.append("[/工具调用结果]\n")

        return "\n".join(parts)

    def _get_conversation_history(
        self, conversation_id: str
    ) -> List[Dict[str, str]]:
        """Get conversation history for a conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        return list(self._conversation_history.get(conversation_id, []))

    def _update_conversation_history(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str
    ) -> None:
        """Update conversation history with a new exchange.

        Args:
            conversation_id: Conversation identifier
            user_message: User's message
            assistant_response: Assistant's response
        """
        if conversation_id not in self._conversation_history:
            self._conversation_history[conversation_id] = []

        history = self._conversation_history[conversation_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_response})

        if len(history) > 20:
            self._conversation_history[conversation_id] = history[-20:]

        logger.debug(
            f"[MEMORY] 📝 更新历史 | conv={conversation_id} | "
            f"消息数={len(self._conversation_history[conversation_id])}"
        )

    def reset_conversation(self, conversation_id: str) -> None:
        """Reset conversation history for a conversation.

        Args:
            conversation_id: Conversation identifier
        """
        if conversation_id in self._conversation_history:
            del self._conversation_history[conversation_id]
            logger.info(f"[MEMORY] 🗑️ 清空历史 | conv={conversation_id}")

    def _add_to_working_memory(
        self,
        conversation_id: str,
        role: str,
        content: str
    ) -> None:
        """添加到工作记忆

        Args:
            conversation_id: 会话ID
            role: 角色 (user/assistant)
            content: 内容
        """
        if conversation_id not in self._conversation_history:
            self._conversation_history[conversation_id] = []

        self._conversation_history[conversation_id].append({
            "role": role,
            "content": content
        })

        if len(self._conversation_history[conversation_id]) > 20:
            self._conversation_history[conversation_id] = \
                self._conversation_history[conversation_id][-20:]

    async def _execute_tools_by_intent(
        self,
        intent_result,
        slots,
        stage_log: Optional[StageLogger] = None
    ) -> Dict[str, Any]:
        """根据意图执行工具

        Args:
            intent_result: 意图识别结果
            slots: 提取的槽位
            stage_log: 阶段日志记录器（可选）

        Returns:
            工具执行结果
        """
        # 获取可用工具
        tools = self._get_tools_for_llm()

        if not tools:
            logger.warning("[TOOLS] ⚠️ 没有可用工具")
            return {}

        logger.info(f"[TOOLS] 🔧 可用工具: {[t['name'] for t in tools]}")

        # 构建消息
        messages = [{"role": "user", "content": self._current_message}]

        try:
            content, tool_calls = await self.llm_client.chat_with_tools(
                messages=messages,
                tools=tools,
                system_prompt=self.system_prompt
            )

            if tool_calls:
                logger.info(
                    f"[TOOLS] 📋 LLM请求调用 {len(tool_calls)} 个工具: "
                    f"{[tc.name for tc in tool_calls]}"
                )

                # 并行执行工具
                start = time.perf_counter()
                results = await self._tool_executor.execute_parallel(tool_calls)
                elapsed = (time.perf_counter() - start) * 1000

                # 统计结果
                success = sum(1 for r in results.values() if not isinstance(r, dict) or "error" not in r)
                failed = sum(1 for r in results.values() if isinstance(r, dict) and "error" in r)

                logger.info(
                    f"[TOOLS] ✅ 并行执行完成 | 成功={success} | 失败={failed} | "
                    f"耗时={elapsed:.2f}ms"
                )
                return results
            else:
                logger.info("[TOOLS] ℹ️ LLM未请求工具调用")
        except Exception as e:
            logger.error(f"[TOOLS] ❌ 工具执行失败: {e}")

        return {}

    async def _build_context(
        self,
        user_id: Optional[str],
        tool_results: Dict[str, Any],
        slots,
        stage_log: Optional[StageLogger] = None
    ) -> str:
        """构建完整上下文

        Args:
            user_id: 用户ID
            tool_results: 工具执行结果
            slots: 槽位信息
            stage_log: 阶段日志记录器（可选）

        Returns:
            格式化的上下文字符串（工具结果、槽位信息等）
        """
        parts = []
        context_parts = []

        # 工具结果
        if tool_results:
            parts.append("## 工具调用结果")
            context_parts.append("## 工具调用结果")
            for name, result in tool_results.items():
                if isinstance(result, dict) and "error" in result:
                    parts.append(f"{name}: 错误 - {result['error']}")
                    context_parts.append(f"{name}: 错误 - {result['error']}")
                else:
                    try:
                        result_str = json.dumps(result, ensure_ascii=False)
                        parts.append(f"{name}: {result_str}")
                        context_parts.append(f"{name}: {result_str}")
                    except Exception:
                        parts.append(f"{name}: {result}")
                        context_parts.append(f"{name}: {result}")

        # 槽位信息
        if slots.destination or slots.start_date:
            parts.append("## 提取的信息")
            context_parts.append("## 提取的信息")
            if slots.destination:
                parts.append(f"- 目的地: {slots.destination}")
                context_parts.append(f"- 目的地: {slots.destination}")
            if slots.start_date:
                parts.append(f"- 日期: {slots.start_date}")
                context_parts.append(f"- 日期: {slots.start_date}")
                if slots.end_date and slots.end_date != slots.start_date:
                    parts.append(f"至 {slots.end_date}")
                    context_parts.append(f"至 {slots.end_date}")

        result = "\n\n".join(parts) if parts else ""

        logger.info(
            f"[CONTEXT] 📚 上下文构建 | "
            f"工具结果={'有' if tool_results else '无'} | "
            f"槽位={slots.destination or '无目的地'} | "
            f"上下文长度={len(result)}字符"
        )
        if stage_log:
            stage_log.end(
                context_length=len(result),
                has_tool_results=bool(tool_results),
                has_slots=bool(slots.destination or slots.start_date)
            )

        return result

    async def _generate_response(
        self,
        context: str,
        user_input: str,
        history: Optional[List[Dict[str, str]]] = None,
        stage_log: Optional[StageLogger] = None
    ) -> AsyncIterator[str]:
        """生成 LLM 响应

        Args:
            context: 构建的上下文
            user_input: 用户输入
            history: 对话历史
            stage_log: 阶段日志记录器

        Yields:
            响应片段
        """
        messages = list(history) if history else []

        if context:
            messages.append({"role": "user", "content": f"{context}\n\n用户: {user_input}"})
        else:
            messages.append({"role": "user", "content": user_input})

        logger.info(
            f"[LLM] 🧠 开始生成响应 | "
            f"上下文长度={len(context)}字符 | "
            f"历史消息数={len(messages)}"
        )

        start = time.perf_counter()
        chunk_count = 0
        first_chunk = True

        async for chunk in self.llm_client.stream_chat(
            messages=messages,
            system_prompt=self.system_prompt
        ):
            chunk_count += 1
            if first_chunk:
                first_chunk_time = (time.perf_counter() - start) * 1000
                logger.info(f"[LLM] ⚡ 首token响应 | 耗时={first_chunk_time:.2f}ms")
                first_chunk = False

            yield chunk

        total_time = (time.perf_counter() - start) * 1000
        logger.info(
            f"[LLM] ✅ 响应生成完成 | "
            f"总耗时={total_time:.2f}ms | "
            f"chunk数={chunk_count}"
        )

        if stage_log:
            stage_log.end(
                total_time_ms=total_time,
                chunk_count=chunk_count
            )

    async def _update_memory_async(
        self,
        user_id: Optional[str],
        conversation_id: str,
        user_input: str,
        assistant_response: str,
        slots,
        stage_log: Optional[StageLogger] = None
    ) -> None:
        """异步更新记忆（后台任务）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            user_input: 用户输入
            assistant_response: 助手响应
            slots: 槽位信息
            stage_log: 阶段日志记录器
        """
        start = time.perf_counter()

        try:
            # TODO: 这里可以添加:
            # 1. 提取用户偏好
            # 2. 更新向量库
            # 3. 记忆晋升

            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"[MEMORY] 💾 异步记忆更新 | conv={conversation_id} | "
                f"耗时={elapsed:.2f}ms"
            )

            if stage_log:
                stage_log.end(elapsed_ms=elapsed)

        except Exception as e:
            logger.error(f"[MEMORY] ❌ 记忆更新失败: {e}")
            if stage_log:
                stage_log.fail(f"记忆更新异常: {e}")

    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """统一处理流程 - 6 步工作流程

        步骤:
        1. 意图 & 槽位识别
        2. 消息基础存储
        3. 按需并行调用工具
        4. 上下文构建
        5. LLM 生成响应
        6. 异步记忆更新

        Args:
            user_input: 用户输入
            conversation_id: 会话ID
            user_id: 用户ID

        Yields:
            响应片段

        Raises:
            AgentError: If LLM client is not configured
        """
        total_start = time.perf_counter()
        self._current_message = user_input

        logger.info(
            f"[WORKFLOW] 🚀 ====== 工作流程开始 ====== | "
            f"conv={conversation_id} | "
            f"user={user_id or 'anonymous'} | "
            f"输入长度={len(user_input)}字符"
        )

        # ===== 阶段 0: 初始化检查 =====
        stage_start = time.perf_counter()
        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:0_INIT] ⏳ 开始 | conv={conversation_id} | "
            f"输入长度={len(user_input)}字符"
        )

        if self.llm_client is None:
            error = "LLM客户端未配置"
            logger.error(
                f"[WORKFLOW:0_INIT] ❌ 失败 | conv={conversation_id} | "
                f"耗时: {elapsed_ms:.2f}ms | 错误: {error}"
            )
            raise AgentError(error, level=DegradationLevel.LLM_DEGRADED)

        logger.info(
            f"[WORKFLOW:0_INIT] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | LLM已配置"
        )

        # ===== 阶段 1: 意图 & 槽位识别 =====
        stage_start = time.perf_counter()
        logger.info(
            f"[WORKFLOW:1_INTENT] ⏳ 开始 | conv={conversation_id} | "
            f"输入: {user_input[:100]}..."
        )

        intent_result = await self._intent_classifier.classify(user_input)
        slots = self._slot_extractor.extract(user_input)

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:1_INTENT] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | "
            f"意图={intent_result.intent} | 置信度={intent_result.confidence:.2f} | "
            f"方法={intent_result.method} | "
            f"目的地={slots.destination or '无'} | 日期={slots.start_date or '无'}"
        )

        # ===== 阶段 2: 消息基础存储 =====
        stage_start = time.perf_counter()
        logger.info(f"[WORKFLOW:2_STORAGE] ⏳ 开始 | conv={conversation_id}")

        history = self._get_conversation_history(conversation_id)
        self._add_to_working_memory(conversation_id, "user", user_input)

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:2_STORAGE] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | "
            f"历史: {len(history)} -> {len(self._conversation_history.get(conversation_id, []))} 条"
        )

        # ===== 阶段 3: 按需并行调用工具 =====
        tool_results: Dict[str, Any] = {}
        stage_start = time.perf_counter()
        logger.info(
            f"[WORKFLOW:3_TOOLS] ⏳ 开始 | conv={conversation_id} | 意图={intent_result.intent}"
        )

        if intent_result.intent in ["itinerary", "query"]:
            logger.info(f"[TOOLS] 🔍 意图={intent_result.intent}，开始工具调用")
            tool_results = await self._execute_tools_by_intent(
                intent_result, slots, None
            )
        else:
            logger.info(f"[TOOLS] ℹ️ 意图={intent_result.intent}，跳过工具调用")

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:3_TOOLS] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 工具调用={len(tool_results)}次"
        )

        # ===== 阶段 4: 上下文构建 =====
        stage_start = time.perf_counter()
        logger.info(f"[WORKFLOW:4_CONTEXT] ⏳ 开始 | conv={conversation_id}")

        context = await self._build_context(
            user_id, tool_results, slots, None
        )

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:4_CONTEXT] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 上下文长度={len(context)}字符"
        )

        # ===== 阶段 5: LLM 生成响应 =====
        full_response = ""
        stage_start = time.perf_counter()
        logger.info(
            f"[WORKFLOW:5_LLM] ⏳ 开始 | conv={conversation_id} | "
            f"上下文长度={len(context)}字符"
        )

        async for chunk in self._generate_response(context, user_input, history, None):
            full_response += chunk
            yield chunk

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:5_LLM] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 响应长度={len(full_response)}字符"
        )

        # 更新工作记忆
        self._add_to_working_memory(conversation_id, "assistant", full_response)

        # ===== 阶段 6: 异步记忆更新 =====
        stage_start = time.perf_counter()
        logger.info(f"[WORKFLOW:6_MEMORY] ⏳ 开始 | conv={conversation_id}")

        asyncio.create_task(
            self._update_memory_async(
                user_id, conversation_id, user_input, full_response, slots, None
            )
        )

        logger.info(
            f"[WORKFLOW:6_MEMORY] ✅ 完成(后台) | conv={conversation_id}"
        )

        # 总耗时统计
        total_time = (time.perf_counter() - total_start) * 1000

        log_workflow_summary(
            conversation_id=conversation_id,
            intent=intent_result.intent,
            tool_calls=len(tool_results),
            total_time_ms=total_time,
            response_length=len(full_response)
        )

        logger.info(
            f"[WORKFLOW] 🏁 ====== 工作流程完成 ====== | "
            f"conv={conversation_id} | "
            f"总耗时={total_time:.2f}ms"
        )

    async def process_simple(
        self,
        user_input: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Process a simple one-shot query without conversation history.

        Useful for standalone queries where conversation context is not needed.

        Args:
            user_input: User's message/input
            system_prompt: Optional custom system prompt

        Returns:
            str: Complete response

        Raises:
            AgentError: If LLM client is not configured
        """
        if self.llm_client is None:
            raise AgentError(
                "LLM client not configured",
                level=DegradationLevel.LLM_DEGRADED
            )

        messages = [{"role": "user", "content": user_input}]
        prompt = system_prompt or self.system_prompt

        return await self.llm_client.chat(messages, system_prompt=prompt)

    async def close(self) -> None:
        """Clean up resources.

        Closes the LLM client if it was created by this engine.
        """
        if self.llm_client is not None:
            await self.llm_client.close()
            logger.info("[QueryEngine] 🔒 LLM客户端已关闭")


# Global default instance (lazy initialization)
_global_engine: Optional[QueryEngine] = None


def get_global_engine() -> QueryEngine:
    """Get or create the global QueryEngine instance.

    Returns:
        QueryEngine: The global engine instance
    """
    global _global_engine
    if _global_engine is None:
        _global_engine = QueryEngine()
    return _global_engine


def set_global_engine(engine: QueryEngine) -> None:
    """Set the global QueryEngine instance.

    Args:
        engine: QueryEngine instance to use as global
    """
    global _global_engine
    _global_engine = engine


__all__ = [
    "QueryEngine",
    "get_global_engine",
    "set_global_engine",
]
