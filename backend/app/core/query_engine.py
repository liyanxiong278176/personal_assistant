"""QueryEngine - Agent Core 总控

提供统一的查询处理入口，集成 LLM 客户端和工具调用功能。
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

logger = logging.getLogger(__name__)


class QueryEngine:
    """QueryEngine - Agent Core 总控

    负责处理所有用户查询，协调工具调用和 LLM 调用。

    流程（Function Calling 模式）:
    1. LLM 分析用户输入，决定是否需要调用工具
    2. 如果需要工具调用，执行工具获取结果
    3. 将工具结果拼接到上下文中
    4. LLM 基于工具结果生成最终回答
    5. 流式返回响应
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

    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Process a user query with Function Calling support.

        流程:
        1. LLM 分析用户输入，决定是否需要调用工具
        2. 如果需要工具调用，执行工具获取结果
        3. 将工具结果拼接到上下文中
        4. LLM 基于工具结果生成最终回答

        Args:
            user_input: User's message/input
            conversation_id: Unique conversation identifier
            user_id: Optional user identifier for personalization

        Yields:
            str: Response chunks for streaming

        Raises:
            AgentError: If LLM client is not configured
        """
        logger.info(
            f"[QueryEngine] Processing query for conversation {conversation_id}"
        )

        if self.llm_client is None:
            logger.error("[QueryEngine] Cannot process: no LLM client configured")
            raise AgentError(
                "LLM client not configured. Please set an LLM client first.",
                level=DegradationLevel.LLM_DEGRADED
            )

        # 获取可用工具
        tools = self._get_tools_for_llm()

        # 构建消息列表（包含对话历史）
        messages = self._get_conversation_history(conversation_id)
        messages.append({"role": "user", "content": user_input})

        # 第一轮：LLM 决定是否调用工具
        tool_results: Dict[str, Any] = {}
        first_response_content = ""

        if tools:
            # 有工具时，使用 Function Calling
            logger.debug(f"[QueryEngine] Available tools: {[t['name'] for t in tools]}")

            try:
                content, tool_calls = await self.llm_client.chat_with_tools(
                    messages=messages,
                    tools=tools,
                    system_prompt=self.system_prompt
                )
                first_response_content = content

                if tool_calls:
                    # 执行工具调用
                    logger.info(f"[QueryEngine] LLM requested {len(tool_calls)} tool calls")
                    tool_results = await self._execute_tool_calls(tool_calls)

                    # 将工具结果添加到消息上下文
                    tool_context = self._format_tool_results_for_context(tool_results)

                    # 构建第二轮消息
                    second_round_messages = list(messages)
                    if first_response_content:
                        second_round_messages.append({"role": "assistant", "content": first_response_content})
                    second_round_messages.append({
                        "role": "user",
                        "content": f"工具调用已完成，请基于以下结果生成回答：{tool_context}"
                    })

                    # 第二轮：基于工具结果生成最终回答
                    full_response = ""
                    async for chunk in self.llm_client.stream_chat(
                        messages=second_round_messages,
                        system_prompt=self.system_prompt
                    ):
                        full_response += chunk
                        yield chunk

                    # 更新对话历史（保存两轮）
                    self._update_conversation_history(
                        conversation_id, user_input, full_response
                    )
                    return

            except Exception as e:
                logger.error(f"[QueryEngine] Function calling failed: {e}")
                # 降级到普通聊天
                pass

        # 没有工具或工具调用失败时的普通聊天流程
        full_response = ""
        try:
            async for chunk in self.llm_client.stream_chat(
                messages=messages,
                system_prompt=self.system_prompt
            ):
                full_response += chunk
                yield chunk

            # 更新对话历史
            self._update_conversation_history(
                conversation_id, user_input, full_response
            )

        except AgentError:
            raise
        except Exception as e:
            logger.error(f"[QueryEngine] Unexpected error: {e}")
            raise AgentError(f"查询处理失败: {e}")

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
