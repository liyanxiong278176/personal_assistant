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
from typing import AsyncIterator, Optional, List, Dict, Any, Union

from .llm import LLMClient, ToolCall
from .prompts import DEFAULT_SYSTEM_PROMPT
from .errors import AgentError, DegradationLevel
from .tools import ToolRegistry, global_registry
from .tools.executor import ToolExecutor
from .intent import IntentClassifier, SlotExtractor, intent_classifier

logger = logging.getLogger(__name__)


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

        if self.llm_client is None:
            logger.warning(
                "[QueryEngine] No LLM client provided, "
                "queries will fail until client is set via set_llm_client()"
            )

    def set_llm_client(self, llm_client: LLMClient) -> None:
        """Set or update the LLM client.

        Args:
            llm_client: LLM client instance
        """
        self.llm_client = llm_client
        logger.info("[QueryEngine] LLM client updated")

    def set_tool_registry(self, tool_registry: ToolRegistry) -> None:
        """Set or update the tool registry.

        Args:
            tool_registry: Tool registry instance
        """
        self._tool_registry = tool_registry
        self._tool_executor = ToolExecutor(tool_registry)
        logger.info("[QueryEngine] Tool registry updated")

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
                    "properties": {},  # 可以扩展为从工具获取参数定义
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
                logger.info(f"[QueryEngine] Executing tool: {call.name} with args: {call.arguments}")
                result = await self._tool_executor.execute(
                    call.name,
                    **call.arguments
                )
                results[call.name] = result
                logger.info(f"[QueryEngine] Tool {call.name} completed")
            except Exception as e:
                logger.error(f"[QueryEngine] Tool {call.name} failed: {e}")
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
                # 尝试格式化结果
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
        # Return a copy to avoid in-place modifications
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

        # Keep last 20 messages to manage context window
        history = self._conversation_history[conversation_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_response})

        # Trim to last 20 messages (10 exchanges)
        if len(history) > 20:
            self._conversation_history[conversation_id] = history[-20:]

        logger.debug(
            f"[QueryEngine] Updated history for {conversation_id}, "
            f"now has {len(self._conversation_history[conversation_id])} messages"
        )

    def reset_conversation(self, conversation_id: str) -> None:
        """Reset conversation history for a conversation.

        Args:
            conversation_id: Conversation identifier
        """
        if conversation_id in self._conversation_history:
            del self._conversation_history[conversation_id]
            logger.info(f"[QueryEngine] Reset conversation {conversation_id}")

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

        # 限制历史长度
        if len(self._conversation_history[conversation_id]) > 20:
            self._conversation_history[conversation_id] = \
                self._conversation_history[conversation_id][-20:]

    async def _execute_tools_by_intent(
        self,
        intent_result,
        slots
    ) -> Dict[str, Any]:
        """根据意图执行工具

        Args:
            intent_result: 意图识别结果
            slots: 提取的槽位

        Returns:
            工具执行结果
        """
        # 获取可用工具
        tools = self._get_tools_for_llm()

        if not tools:
            return {}

        # 构建消息
        messages = [{"role": "user", "content": self._current_message}]

        # 使用 LLM Function Calling 决定工具调用
        try:
            content, tool_calls = await self.llm_client.chat_with_tools(
                messages=messages,
                tools=tools,
                system_prompt=self.system_prompt
            )

            if tool_calls:
                # 并行执行工具
                logger.info(
                    f"[QueryEngine] Executing {len(tool_calls)} tool calls "
                    f"for intent {intent_result.intent}"
                )
                return await self._tool_executor.execute_parallel(tool_calls)
        except Exception as e:
            logger.error(f"[QueryEngine] Tool execution failed: {e}")

        return {}

    async def _build_context(
        self,
        user_id: Optional[str],
        tool_results: Dict[str, Any],
        slots
    ) -> str:
        """构建完整上下文

        Args:
            user_id: 用户ID
            tool_results: 工具执行结果
            slots: 槽位信息

        Returns:
            格式化的上下文字符串（工具结果、槽位信息等）
        """
        parts = []

        # 工具结果
        if tool_results:
            parts.append("## 工具调用结果")
            for name, result in tool_results.items():
                if isinstance(result, dict) and "error" in result:
                    parts.append(f"{name}: 错误 - {result['error']}")
                else:
                    try:
                        result_str = json.dumps(result, ensure_ascii=False)
                        parts.append(f"{name}: {result_str}")
                    except Exception:
                        parts.append(f"{name}: {result}")

        # 槽位信息
        if slots.destination or slots.start_date:
            parts.append("## 提取的信息")
            if slots.destination:
                parts.append(f"- 目的地: {slots.destination}")
            if slots.start_date:
                parts.append(f"- 日期: {slots.start_date}")
                if slots.end_date and slots.end_date != slots.start_date:
                    parts.append(f"至 {slots.end_date}")

        # 注: 对话历史直接作为 LLM 消息传递，不包含在 context 字符串中

        return "\n\n".join(parts) if parts else ""

    async def _generate_response(
        self,
        context: str,
        user_input: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncIterator[str]:
        """生成 LLM 响应

        Args:
            context: 构建的上下文
            user_input: 用户输入
            history: 对话历史

        Yields:
            响应片段
        """
        messages = list(history) if history else []

        if context:
            messages.append({"role": "user", "content": f"{context}\n\n用户: {user_input}"})
        else:
            messages.append({"role": "user", "content": user_input})

        async for chunk in self.llm_client.stream_chat(
            messages=messages,
            system_prompt=self.system_prompt
        ):
            yield chunk

    async def _update_memory_async(
        self,
        user_id: Optional[str],
        conversation_id: str,
        user_input: str,
        assistant_response: str,
        slots
    ) -> None:
        """异步更新记忆（后台任务）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            user_input: 用户输入
            assistant_response: 助手响应
            slots: 槽位信息
        """
        try:
            # TODO: 这里可以添加:
            # 1. 提取用户偏好
            # 2. 更新向量库
            # 3. 记忆晋升

            logger.debug(f"[QueryEngine] Memory update task for {conversation_id}")
        except Exception as e:
            logger.error(f"[QueryEngine] Memory update failed: {e}")

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
        logger.info(f"[QueryEngine] Processing: {user_input[:50]}...")

        if self.llm_client is None:
            raise AgentError(
                "LLM client not configured",
                level=DegradationLevel.LLM_DEGRADED
            )

        # 保存当前消息供后续使用
        self._current_message = user_input

        # ===== 步骤 1: 意图 & 槽位识别 =====
        intent_result = await self._intent_classifier.classify(user_input)
        slots = self._slot_extractor.extract(user_input)

        logger.info(
            f"[QueryEngine] Intent: {intent_result.intent} "
            f"(confidence: {intent_result.confidence}, method: {intent_result.method})"
        )
        logger.debug(f"[QueryEngine] Slots: destination={slots.destination}, "
                    f"dates={slots.start_date}-{slots.end_date}")

        # ===== 步骤 2: 消息基础存储 =====
        # 注: 实际的存储由调用者 (agent_service) 处理
        # 这里只记录到工作记忆
        # 获取历史记录（在添加当前消息之前）
        history = self._get_conversation_history(conversation_id)

        # 添加当前消息到工作记忆
        self._add_to_working_memory(conversation_id, "user", user_input)

        # ===== 步骤 3: 按需并行调用工具 =====
        tool_results: Dict[str, Any] = {}
        if intent_result.intent in ["itinerary", "query"]:
            tool_results = await self._execute_tools_by_intent(
                intent_result, slots
            )

        # ===== 步骤 4: 上下文构建 =====
        context = await self._build_context(
            user_id, tool_results, slots
        )

        # ===== 步骤 5: LLM 生成响应 =====
        full_response = ""
        async for chunk in self._generate_response(context, user_input, history):
            full_response += chunk
            yield chunk

        # 更新工作记忆
        self._add_to_working_memory(conversation_id, "assistant", full_response)

        # ===== 步骤 6: 异步记忆更新 =====
        # 注: 实际的持久化由调用者处理
        # 这里只创建后台任务
        asyncio.create_task(
            self._update_memory_async(
                user_id, conversation_id, user_input, full_response, slots
            )
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
            logger.info("[QueryEngine] Closed LLM client")


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
