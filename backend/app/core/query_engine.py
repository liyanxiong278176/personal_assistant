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

from pathlib import Path

from .llm import LLMClient, ToolCall
from .prompts import DEFAULT_SYSTEM_PROMPT
from .errors import AgentError, DegradationLevel
from .tools import ToolRegistry, global_registry
from .tools.executor import ToolExecutor
from .intent import IntentClassifier, SlotExtractor, intent_classifier
from .context.guard import ContextGuard
from .context.config import ContextConfig
from .session import SessionInitializer
from .subagent import SubAgentOrchestrator, ResultBubble, AgentType

logger = logging.getLogger(__name__)


class WorkflowStage(Enum):
    """工作流程阶段枚举"""
    STAGE_0_INIT = "0_INIT"           # 初始化
    STAGE_1_INTENT = "1_INTENT"       # 意图识别
    STAGE_2_STORAGE = "2_STORAGE"     # 消息存储
    STAGE_3_CTX_CLEAN = "3_CTX_CLEAN"  # 上下文前置清理
    STAGE_4_TOOLS = "4_TOOLS"         # 工具执行
    STAGE_5_CONTEXT = "5_CONTEXT"     # 上下文构建
    STAGE_6_LLM = "6_LLM"             # LLM响应生成
    STAGE_7_CTX_MANAGE = "7_CTX_MANAGE"  # 上下文后置管理
    STAGE_8_MEMORY = "8_MEMORY"       # 记忆更新
    COMPLETE = "COMPLETE"            # 完成


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
        tool_registry: Optional[ToolRegistry] = None,
        config_path: Optional[Path] = None
    ):
        """Initialize QueryEngine.

        Args:
            llm_client: LLM 客户端实例，为 None 时创建默认实例
            system_prompt: 系统提示词，为 None 时使用默认值
            tool_registry: 工具注册表，为 None 时使用全局注册表
            config_path: 会话配置文件路径
        """
        self.llm_client = llm_client
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._tool_registry = tool_registry or global_registry
        self._tool_executor = ToolExecutor(self._tool_registry)
        self._conversation_history: Dict[str, List[Dict[str, str]]] = {}

        # 意图分类器和槽位提取器
        self._intent_classifier = intent_classifier
        self._slot_extractor = SlotExtractor()

        # === 上下文守卫初始化 ===
        rules_cache = ContextConfig.load_rules_at_startup(
            Path("docs/superpowers/")
        )
        context_config = ContextConfig(rules_cache=rules_cache)
        self.context_guard = ContextGuard(
            config=context_config,
            llm_client=self.llm_client,
        )

        # === 会话生命周期组件初始化 ===
        self._session_initializer = SessionInitializer(
            config_path=config_path,
            custom_rules=None
        )
        self._max_total_retries = 5
        # 跟踪已初始化的会话，避免重复初始化
        self._initialized_sessions: set[str] = set()

        # === Phase 4: 多Agent系统初始化 ===
        self._subagent_orchestrator = SubAgentOrchestrator()

        # === Phase 2: 持久化组件初始化 ===
        self._phase2_enabled = False
        self._phase2_initialized = False
        self._phase2_init_lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task] = set()
        # 延迟初始化，不在 __init__ 中执行

        logger.info(
            f"[QueryEngine] 🚀 初始化完成 | "
            f"工具数量={len(self._tool_registry.list_tools())} | "
            f"LLM客户端={'已配置' if llm_client else '未配置'} | "
            f"会话生命周期={'已启用' if self._session_initializer else '未启用'}"
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

        # 清理会话初始化状态
        if conversation_id in self._initialized_sessions:
            self._initialized_sessions.discard(conversation_id)
            logger.info(f"[MEMORY] 🗑️ 清空会话初始化状态 | conv={conversation_id}")

        # 重置重试状态
        self._session_initializer.retry_manager.reset(conversation_id)

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
        stage_log: Optional[StageLogger] = None,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        """生成 LLM 响应

        Args:
            context: 构建的上下文
            user_input: 用户输入
            history: 对话历史（仅当 messages 未提供时使用）
            stage_log: 阶段日志记录器
            messages: 预构建的消息列表（推荐，避免内部修改 history）

        Yields:
            响应片段
        """
        # 使用预构建的消息列表（如果提供），否则从 history 构建
        if messages is not None:
            llm_messages = messages
        else:
            # 从 history 构建时使用副本，避免修改原始历史
            llm_messages = list(history) if history else []
            new_msg = {
                "role": "user",
                "content": f"{context}\n\n用户: {user_input}" if context else user_input
            }
            llm_messages.append(new_msg)

        logger.info(
            f"[LLM] 🧠 开始生成响应 | "
            f"上下文长度={len(context)}字符 | "
            f"历史消息数={len(llm_messages)}"
        )

        start = time.perf_counter()
        chunk_count = 0
        first_chunk = True

        async for chunk in self.llm_client.stream_chat(
            messages=llm_messages,
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
        """异步更新记忆（后台任务）- Phase 2 集成版本

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            user_input: 用户输入
            assistant_response: 助手响应
            slots: 槽位信息
            stage_log: 阶段日志记录器
        """
        import time
        from uuid import uuid4

        start = time.perf_counter()

        # 确保 Phase 2 组件已初始化
        await self._ensure_phase2_initialized()

        if not self._phase2_enabled:
            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"[MEMORY] ⚠️ Phase2未启用，跳过持久化 | conv={conversation_id} | "
                f"耗时={elapsed:.2f}ms"
            )
            return

        try:
            logger.info(f"[MEMORY:Phase2] 🔄 开始异步记忆更新 | conv={conversation_id}")

            # === 步骤 1: 持久化消息到 PostgreSQL ===
            try:
                from app.core.memory.persistence import Message as PersistenceMessage
                from app.db.postgres import create_conversation_ext, get_conversation_ext
                from uuid import UUID

                # 确保 conversation 存在（使用字符串 ID 转换为 UUID）
                conv_uuid = UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id

                # 检查 conversation 是否存在，不存在则创建
                async with self._message_repo._get_db_connection() as conn:
                    existing = await get_conversation_ext(conn, conv_uuid)
                    if not existing:
                        await create_conversation_ext(conn, conv_uuid, "对话")

                # 保存用户消息
                user_msg = PersistenceMessage(
                    id=uuid4(),
                    conversation_id=conv_uuid,
                    user_id=user_id or "unknown",
                    role="user",
                    content=user_input
                )

                await self._persistence_manager.persist_message(user_msg)
                logger.debug(f"[MEMORY:Phase2] ✓ 用户消息已入队持久化 | conv={conversation_id}")

                # 保存助手响应
                assistant_msg = PersistenceMessage(
                    id=uuid4(),
                    conversation_id=conv_uuid,
                    user_id=user_id or "unknown",
                    role="assistant",
                    content=assistant_response,
                    tokens=len(assistant_response) // 4  # 粗略估算
                )

                await self._persistence_manager.persist_message(assistant_msg)
                logger.debug(f"[MEMORY:Phase2] ✓ 助手消息已入队持久化 | conv={conversation_id}")

            except Exception as e:
                logger.error(f"[MEMORY:Phase2] ❌ 消息持久化失败: {e}")

            # === 步骤 2: 提取并保存语义记忆 ===
            try:
                from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
                from app.db.vector_store import ChineseEmbeddings

                embedder = ChineseEmbeddings()

                # 检查是否包含偏好/意图信息
                if self._should_save_as_semantic(user_input, assistant_response):
                    # 提取用户偏好
                    memory_content = f"用户: {user_input}\n助手: {assistant_response[:100]}..."

                    memory = MemoryItem(
                        content=memory_content,
                        level=MemoryLevel.SEMANTIC,
                        memory_type=MemoryType.PREFERENCE,
                        importance=0.7,
                        metadata={
                            "user_id": user_id or "unknown",
                            "conversation_id": conversation_id,
                            "created_at": time.time()
                        }
                    )

                    # 获取向量并保存
                    embedding = embedder.embed_query(memory_content)
                    await self._semantic_repo.add(
                        content=memory_content,
                        embedding=embedding,
                        metadata=memory.metadata
                    )
                    logger.debug(f"[MEMORY:Phase2] ✓ 语义记忆已保存 | type=preference")

            except Exception as e:
                logger.error(f"[MEMORY:Phase2] ❌ 语义记忆保存失败: {e}")

            # === 步骤 3: 更新情景记忆 ===
            try:
                from app.core.memory.hierarchy import MemoryItem, MemoryLevel

                episodic_memory = MemoryItem(
                    content=f"对话摘要: {user_input[:100]}... → {assistant_response[:100]}...",
                    level=MemoryLevel.EPISODIC,
                    memory_type=MemoryType.STATE,
                    importance=0.5,
                    metadata={
                        "user_id": user_id or "unknown",
                        "conversation_id": conversation_id,
                        "last_message": user_input,
                        "last_response": assistant_response[:200]
                    }
                )

                # add() 是同步方法，不需要 await
                self._memory_hierarchy.add(episodic_memory)
                logger.debug(f"[MEMORY:Phase2] ✓ 情景记忆已更新 | level=episodic")

            except Exception as e:
                logger.error(f"[MEMORY:Phase2] ❌ 情景记忆更新失败: {e}")

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[MEMORY:Phase2] ✅ 记忆更新完成 | conv={conversation_id} | "
                f"耗时={elapsed:.2f}ms"
            )

            if stage_log:
                stage_log.end(elapsed_ms=elapsed)

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[MEMORY:Phase2] ❌ 记忆更新失败 | conv={conversation_id} | "
                f"耗时={elapsed:.2f}ms | 错误={e}"
            )
            if stage_log:
                stage_log.fail(f"记忆更新异常: {e}")

    def _should_save_as_semantic(self, user_input: str, response: str) -> bool:
        """判断是否应该保存为语义记忆

        Args:
            user_input: 用户输入
            response: 助手响应

        Returns:
            是否应该保存
        """
        # 简单规则：如果包含目的地、预算、偏好等关键词，则保存
        keywords = ["去", "想", "预算", "喜欢", "推荐", "计划", "希望"]
        return any(kw in user_input for kw in keywords) or any(kw in response for kw in keywords)

    async def _process_single_attempt(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> tuple[str, Optional[object], Optional[Dict[str, Any]]]:
        """单次工作流程执行 (内部方法，供重试循环调用)

        Returns:
            (full_response, intent_result, tool_results)
            成功时 intent_result 和 tool_results 有值，full_response 为响应文本
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

        clean_history = self._get_conversation_history(conversation_id)
        self._add_to_working_memory(conversation_id, "user", user_input)
        history = self._get_conversation_history(conversation_id)

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:2_STORAGE] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | "
            f"历史: {len(history)} 条"
        )

        # ===== 阶段 3: 上下文前置清理 =====
        stage_start = time.perf_counter()
        logger.info(f"[WORKFLOW:3_CTX_CLEAN] ⏳ 开始 | conv={conversation_id}")

        history = await self.context_guard.pre_process(history)

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:3_CTX_CLEAN] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 历史: {len(history)} 条"
        )

        # ===== 阶段 4: 按需并行调用工具 / 多Agent派生 =====
        tool_results: Dict[str, Any] = {}
        stage_start = time.perf_counter()
        logger.info(
            f"[WORKFLOW:4_TOOLS] ⏳ 开始 | conv={conversation_id} | 意图={intent_result.intent}"
        )

        if intent_result.intent in ["itinerary", "query"]:
            # 检查是否需要派生子Agent（复杂度 >= 5）
            slots_dict = slots.__dict__ if hasattr(slots, '__dict__') else {}
            session_state = self._conversation_history.get(conversation_id)

            if self._subagent_orchestrator.should_spawn_subagents(slots_dict, session_state):
                logger.info(f"[WORKFLOW:4_TOOLS] 🔄 多Agent模式 | conv={conversation_id}")

                # 确定Agent类型
                agent_types = []
                if slots_dict.get("destinations") or slots_dict.get("destination"):
                    agent_types.append(AgentType.ROUTE)
                if slots_dict.get("need_hotel"):
                    agent_types.append(AgentType.HOTEL)
                if slots_dict.get("need_weather"):
                    agent_types.append(AgentType.WEATHER)
                if agent_types:  # 有其他Agent时，通常需要预算
                    agent_types.append(AgentType.BUDGET)

                # 派生并执行
                sessions = await self._subagent_orchestrator.spawn_subagents(
                    agent_types=agent_types,
                    parent_session=session_state,
                    slots=slots_dict,
                    llm_client=self.llm_client
                )

                # 结果冒泡
                bubble = ResultBubble(parent_session_id=conversation_id)
                stats = await bubble.bubble_up(sessions, tool_results)

                logger.info(
                    f"[WORKFLOW:4_TOOLS] 多Agent完成 | 成功={stats.successful} | 失败={stats.failed}"
                )
            else:
                # 单Agent模式：原有逻辑
                logger.info(f"[WORKFLOW:4_TOOLS] 🔧 单Agent模式 | conv={conversation_id}")
                tool_results = await self._execute_tools_by_intent(
                    intent_result, slots, None
                )
        else:
            logger.info(f"[TOOLS] ℹ️ 意图={intent_result.intent}，跳过工具调用")

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:4_TOOLS] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 工具调用={len(tool_results)}次"
        )

        # ===== 阶段 5: 上下文构建 =====
        stage_start = time.perf_counter()
        logger.info(f"[WORKFLOW:5_CONTEXT] ⏳ 开始 | conv={conversation_id}")

        context = await self._build_context(
            user_id, tool_results, slots, None
        )

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:5_CONTEXT] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 上下文长度={len(context)}字符"
        )

        # ===== 阶段 6: LLM 生成响应 =====
        full_response = ""
        stage_start = time.perf_counter()
        logger.info(
            f"[WORKFLOW:6_LLM] ⏳ 开始 | conv={conversation_id} | "
            f"上下文长度={len(context)}字符"
        )

        llm_messages = list(clean_history) if clean_history else []
        if context:
            llm_messages.append({"role": "user", "content": f"{context}\n\n用户: {user_input}"})
        else:
            llm_messages.append({"role": "user", "content": user_input})

        async for chunk in self._generate_response(context, user_input, clean_history, None, messages=llm_messages):
            full_response += chunk

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:6_LLM] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 响应长度={len(full_response)}字符"
        )

        # 更新工作记忆
        self._add_to_working_memory(conversation_id, "assistant", full_response)

        # ===== 阶段 7: 上下文后置管理 =====
        stage_start = time.perf_counter()
        logger.info(f"[WORKFLOW:7_CTX_MANAGE] ⏳ 开始 | conv={conversation_id}")

        history = await self.context_guard.post_process(history)

        elapsed_ms = (time.perf_counter() - stage_start) * 1000
        logger.info(
            f"[WORKFLOW:7_CTX_MANAGE] ✅ 完成 | conv={conversation_id} | "
            f"耗时: {elapsed_ms:.2f}ms | 历史: {len(history)} 条"
        )

        # ===== 阶段 8: 异步记忆更新 =====
        stage_start = time.perf_counter()
        logger.info(f"[WORKFLOW:8_MEMORY] ⏳ 开始 | conv={conversation_id}")

        task = asyncio.create_task(
            self._update_memory_async(
                user_id, conversation_id, user_input, full_response, slots, None
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        logger.info(
            f"[WORKFLOW:8_MEMORY] ✅ 完成(后台) | conv={conversation_id}"
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

        return full_response, intent_result, tool_results

    async def _process_streaming_attempt(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """流式工作流程执行 - 直接yield LLM chunks而不是收集成字符串

        Steps 1-5: 意图识别、工具调用、上下文构建
        Step 6: 流式LLM生成（直接yield）
        Steps 7-8: 后处理和记忆更新

        Yields:
            LLM响应片段
        """
        total_start = time.perf_counter()
        self._current_message = user_input

        logger.info(
            f"[WORKFLOW:STREAM] 🚀 ====== 流式工作流程开始 ====== | "
            f"conv={conversation_id} | "
            f"user={user_id or 'anonymous'}"
        )

        # ===== 阶段 0: 初始化检查 =====
        if self.llm_client is None:
            error = "LLM客户端未配置"
            logger.error(f"[WORKFLOW:STREAM] ❌ 失败 | {error}")
            raise AgentError(error, level=DegradationLevel.LLM_DEGRADED)

        # ===== 阶段 1: 意图 & 槽位识别 =====
        logger.info(f"[WORKFLOW:STREAM:1_INTENT] ⏳ 开始 | 输入: {user_input[:50]}...")

        intent_result = await self._intent_classifier.classify(user_input)
        slots = self._slot_extractor.extract(user_input)

        logger.info(
            f"[WORKFLOW:STREAM:1_INTENT] ✅ 完成 | "
            f"意图={intent_result.intent} | 置信度={intent_result.confidence:.2f}"
        )

        # ===== 阶段 2: 消息基础存储 =====
        logger.info(f"[WORKFLOW:STREAM:2_STORAGE] ⏳ 开始")

        clean_history = self._get_conversation_history(conversation_id)
        self._add_to_working_memory(conversation_id, "user", user_input)
        history = self._get_conversation_history(conversation_id)

        logger.info(
            f"[WORKFLOW:STREAM:2_STORAGE] ✅ 完成 | 历史: {len(history)} 条"
        )

        # ===== 阶段 3: 上下文前置清理 =====
        logger.info(f"[WORKFLOW:STREAM:3_CTX_CLEAN] ⏳ 开始")

        history = await self.context_guard.pre_process(history)

        logger.info(f"[WORKFLOW:STREAM:3_CTX_CLEAN] ✅ 完成")

        # ===== 阶段 4: 按需并行调用工具 / 多Agent派生 =====
        tool_results: Dict[str, Any] = {}
        logger.info(f"[WORKFLOW:STREAM:4_TOOLS] ⏳ 开始 | 意图={intent_result.intent}")

        if intent_result.intent in ["itinerary", "query"]:
            # 检查是否需要派生子Agent（复杂度 >= 5）
            slots_dict = slots.__dict__ if hasattr(slots, '__dict__') else {}
            session_state = self._conversation_history.get(conversation_id)

            if self._subagent_orchestrator.should_spawn_subagents(slots_dict, session_state):
                logger.info(f"[WORKFLOW:STREAM:4_TOOLS] 🔄 多Agent模式")

                # 确定Agent类型
                agent_types = []
                if slots_dict.get("destinations") or slots_dict.get("destination"):
                    agent_types.append(AgentType.ROUTE)
                if slots_dict.get("need_hotel"):
                    agent_types.append(AgentType.HOTEL)
                if slots_dict.get("need_weather"):
                    agent_types.append(AgentType.WEATHER)
                if agent_types:
                    agent_types.append(AgentType.BUDGET)

                # 派生并执行
                sessions = await self._subagent_orchestrator.spawn_subagents(
                    agent_types=agent_types,
                    parent_session=session_state,
                    slots=slots_dict,
                    llm_client=self.llm_client
                )

                # 结果冒泡
                bubble = ResultBubble(parent_session_id=conversation_id)
                stats = await bubble.bubble_up(sessions, tool_results)

                logger.info(
                    f"[WORKFLOW:STREAM:4_TOOLS] 多Agent完成 | 成功={stats.successful}"
                )
            else:
                # 单Agent模式
                logger.info(f"[WORKFLOW:STREAM:4_TOOLS] 🔧 单Agent模式")
                tool_results = await self._execute_tools_by_intent(
                    intent_result, slots, None
                )
        else:
            logger.info(f"[WORKFLOW:STREAM:4_TOOLS] ℹ️ 意图={intent_result.intent}，跳过工具")

        logger.info(
            f"[WORKFLOW:STREAM:4_TOOLS] ✅ 完成 | 工具调用={len(tool_results)}次"
        )

        # ===== 阶段 5: 上下文构建 =====
        logger.info(f"[WORKFLOW:STREAM:5_CONTEXT] ⏳ 开始")

        context = await self._build_context(
            user_id, tool_results, slots, None
        )

        logger.info(
            f"[WORKFLOW:STREAM:5_CONTEXT] ✅ 完成 | 上下文长度={len(context)}字符"
        )

        # ===== 阶段 6: 流式LLM生成响应 =====
        logger.info(f"[WORKFLOW:STREAM:6_LLM] ⏳ 开始 | 流式输出")

        llm_messages = list(clean_history) if clean_history else []
        if context:
            llm_messages.append({"role": "user", "content": f"{context}\n\n用户: {user_input}"})
        else:
            llm_messages.append({"role": "user", "content": user_input})

        full_response = ""
        chunk_count = 0

        # 直接yield LLM chunks，实现真正的流式输出
        async for chunk in self._generate_response(
            context, user_input, clean_history, None, messages=llm_messages
        ):
            chunk_count += 1
            full_response += chunk
            yield chunk  # 流式输出

        logger.info(
            f"[WORKFLOW:STREAM:6_LLM] ✅ 完成 | chunk数={chunk_count} | 响应长度={len(full_response)}"
        )

        # 更新工作记忆
        self._add_to_working_memory(conversation_id, "assistant", full_response)

        # ===== 阶段 7: 上下文后置管理 =====
        logger.info(f"[WORKFLOW:STREAM:7_CTX_MANAGE] ⏳ 开始")

        history = await self.context_guard.post_process(history)

        logger.info(f"[WORKFLOW:STREAM:7_CTX_MANAGE] ✅ 完成")

        # ===== 阶段 8: 异步记忆更新 =====
        logger.info(f"[WORKFLOW:STREAM:8_MEMORY] ⏳ 开始")

        task = asyncio.create_task(
            self._update_memory_async(
                user_id, conversation_id, user_input, full_response, slots, None
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        logger.info(f"[WORKFLOW:STREAM:8_MEMORY] ✅ 完成(后台)")

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
            f"[WORKFLOW:STREAM] 🏁 ====== 流式工作流程完成 ====== | "
            f"conv={conversation_id} | 总耗时={total_time:.2f}ms"
        )

    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """统一处理流程 - 带重试循环

        工作流程：
        - Step 0: 会话初始化（仅首次）
        - 主循环（最多5次重试）：
          - 执行 6 步流程
          - 失败时分类异常
          - 根据策略决定重试或降级

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
        retry_manager = self._session_initializer.retry_manager

        # ===== Phase 3 Step 0: 会话初始化（仅首次） =====
        if conversation_id not in self._initialized_sessions:
            logger.info(
                f"[WORKFLOW:STEP_0] 🚀 会话初始化 | "
                f"conv={conversation_id} | user={user_id or 'anonymous'}"
            )
            try:
                # 如果没有提供 user_id，生成一个临时的
                if user_id is None:
                    from uuid import uuid4
                    user_id = str(uuid4())
                    logger.info(f"[WORKFLOW:STEP_0] 生成临时用户ID: {user_id}")

                session_state = await self._session_initializer.initialize(
                    conversation_id=conversation_id,
                    user_id=user_id
                )

                # 标记会话已初始化
                self._initialized_sessions.add(conversation_id)

                logger.info(
                    f"[WORKFLOW:STEP_0] ✅ 会话初始化完成 | "
                    f"session={session_state.session_id} | "
                    f"context_window={session_state.context_window_size}"
                )
            except Exception as e:
                logger.warning(f"[WORKFLOW:STEP_0] ⚠️ 初始化失败（非致命）: {e}")
                # 初始化失败不阻止工作流程继续

        # ===== 主循环（最多5次重试） =====
        while retry_manager.get_retry_count(conversation_id) < self._max_total_retries:
            try:
                # ===== 执行流式工作流程 =====
                async for chunk in self._process_streaming_attempt(
                    user_input, conversation_id, user_id
                ):
                    yield chunk
                return

            except Exception as e:
                should_retry, count = retry_manager.should_retry(conversation_id, e)

                if not should_retry:
                    # 不允许重试，返回降级响应
                    logger.error(f"[WORKFLOW] ❌ 不可恢复错误: {e}")
                    fallback = self._session_initializer.fallback_handler.get_fallback(e)
                    yield fallback.message
                    return

                # 允许重试，应用退避延迟
                logger.info(f"[WORKFLOW] 🔄 重试 ({count}/{self._max_total_retries}) | error={type(e).__name__}")
                await retry_manager.apply_backoff(count)

        # 超过最大重试次数
        last_error = retry_manager.get_last_error(conversation_id)
        if last_error:
            logger.error(f"[WORKFLOW] ❌ 超过最大重试次数: {last_error}")
            fallback = self._session_initializer.fallback_handler.get_fallback(last_error)
            yield fallback.message

        logger.info(f"[WORKFLOW] ⚠️ 交付降级响应")

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

    async def _ensure_phase2_initialized(self):
        """确保 Phase 2 组件已初始化（延迟初始化）"""
        if self._phase2_initialized:
            return

        async with self._phase2_init_lock:
            # 双重检查
            if self._phase2_initialized:
                return

            try:
                from app.db.postgres import Database
                from app.db.message_repo import PostgresMessageRepository
                from app.db.semantic_repo import ChromaDBSemanticRepository
                from app.db.vector_store import VectorStore
                from app.core.memory.retrieval import HybridRetriever
                from app.core.memory.persistence import AsyncPersistenceManager
                from app.core.memory.hierarchy import MemoryHierarchy
                from app.core.memory.loaders import MemoryLoader

                # 确保 Database 连接池已初始化
                await Database.connect()

                # 向量存储
                self._vector_store = VectorStore()

                # 语义仓储
                self._semantic_repo = ChromaDBSemanticRepository(self._vector_store)

                # 混合检索器
                self._hybrid_retriever = HybridRetriever(self._semantic_repo)

                # 记忆层级
                self._memory_hierarchy = MemoryHierarchy()

                # 记忆加载器
                self._memory_loader = MemoryLoader(self._memory_hierarchy, self._hybrid_retriever)

                # 消息仓储 (使用 Database.connection 上下文管理器)
                self._message_repo = PostgresMessageRepository(Database.connection)

                # 异步持久化管理器
                self._persistence_manager = AsyncPersistenceManager(self._message_repo)

                # 启动持久化管理器
                await self._persistence_manager.start()

                self._phase2_enabled = True
                self._phase2_initialized = True

                logger.info("[QueryEngine:Phase2] ✅ Phase 2 组件已初始化")
                logger.info("[QueryEngine:Phase2]   - MessageRepository: PostgresMessageRepository")
                logger.info("[QueryEngine:Phase2]   - SemanticRepository: ChromaDBSemanticRepository")
                logger.info("[QueryEngine:Phase2]   - HybridRetriever: 已配置")
                logger.info("[QueryEngine:Phase2]   - MemoryHierarchy: 已初始化")
                logger.info("[QueryEngine:Phase2]   - PersistenceManager: 已启动")

            except ImportError as e:
                logger.warning(f"[QueryEngine:Phase2] ⚠️ Phase 2 组件导入失败: {e}")
                self._phase2_enabled = False
                self._phase2_initialized = True  # 标记为已尝试初始化
            except Exception as e:
                logger.error(f"[QueryEngine:Phase2] ❌ Phase 2 初始化失败: {e}")
                self._phase2_enabled = False
                self._phase2_initialized = True  # 标记为已尝试初始化

    async def close(self) -> None:
        """Clean up resources.

        Closes the LLM client and stops the persistence manager if initialized.
        """
        # Cancel all pending background tasks
        if hasattr(self, '_background_tasks') and self._background_tasks:
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()

        # Wait for all tasks to complete/cancel
        if hasattr(self, '_background_tasks') and self._background_tasks:
            pending = [t for t in self._background_tasks if not t.done()]
            if pending:
                logger.info(f"[QueryEngine] ⏳ 等待 {len(pending)} 个后台任务...")
                await asyncio.gather(*pending, return_exceptions=True)
                self._background_tasks.clear()

        # 停止 Phase 2 持久化管理器
        if self._phase2_initialized and hasattr(self, '_persistence_manager'):
            try:
                await self._persistence_manager.stop()
                logger.info("[QueryEngine:Phase2] 🛑 持久化管理器已停止")
            except Exception as e:
                logger.error(f"[QueryEngine:Phase2] ❌ 停止持久化管理器失败: {e}")

        # 关闭 LLM 客户端
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
