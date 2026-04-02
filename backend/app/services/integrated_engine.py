"""集成 Agent Core 到现有工作流程

这个模块将 Agent Core 的 QueryEngine 与现有的服务
（llm_service, itinerary_agent, memory_service 等）集成。
"""

import logging
from typing import Optional

from app.core import (
    QueryEngine, Tool, ToolRegistry,
    get_slash_registry, get_skill_registry
)
from app.core.llm import LLMClient
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class IntegratedLLMClient(LLMClient):
    """包装现有 LLMService 的客户端"""

    async def stream_chat(self, messages, system_prompt=None):
        """使用现有 llm_service 进行流式聊天"""
        # 将消息格式转换为 llm_service 期望的格式
        user_message = messages[-1]["content"] if messages else ""

        # 构建自定义系统提示词（如果有）
        custom_prompt = None
        if system_prompt:
            # 从系统提示词中提取关键部分
            custom_prompt = system_prompt

        # 使用现有的 llm_service
        async for chunk in llm_service.stream_chat(
            user_message=user_message,
            conversation_id=None,  # 由调用者管理
            custom_system_prompt=custom_prompt
        ):
            yield chunk


class IntegratedQueryEngine(QueryEngine):
    """集成式 QueryEngine，协调现有服务"""

    def __init__(self):
        # 使用包装的 LLM 客户端
        llm_client = IntegratedLLMClient()
        super().__init__(llm_client=llm_client)

        # 注册现有服务作为工具（延迟注册，避免循环导入）
        self._services_registered = False

    def register_services(self, itinerary_agent=None, memory_service=None, preference_service=None):
        """注册现有服务作为工具"""
        if self._services_registered:
            return

        from app.core.tools import global_registry

        # 注册行程规划工具
        if itinerary_agent:
            class ItineraryTool(Tool):
                @property
                def name(self):
                    return "generate_itinerary"

                @property
                def description(self):
                    return "生成旅行行程规划"

                async def execute(self, destination: str, start_date: str, end_date: str, **kwargs):
                    return await itinerary_agent.generate_itinerary(
                        destination=destination,
                        start_date=start_date,
                        end_date=end_date,
                        **kwargs
                    )

            global_registry.register(ItineraryTool())
            logger.info("[IntegratedQueryEngine] Registered itinerary tool")

        # 注册记忆工具
        if memory_service:
            class MemoryTool(Tool):
                @property
                def name(self):
                    return "search_memory"

                @property
                def description(self):
                    return "搜索用户历史记忆"

                async def execute(self, query: str, user_id: str, **kwargs):
                    return await memory_service.search_memories(user_id, query)

            global_registry.register(MemoryTool())
            logger.info("[IntegratedQueryEngine] Registered memory tool")

        # 注册偏好管理工具
        if preference_service:
            class PreferenceTool(Tool):
                @property
                def name(self):
                    return "get_preferences"

                @property
                def description(self):
                    return "获取用户偏好设置"

                async def execute(self, user_id: str, **kwargs):
                    return await preference_service.get_user_preferences(user_id)

            global_registry.register(PreferenceTool())
            logger.info("[IntegratedQueryEngine] Registered preference tool")

        self._services_registered = True

    async def process_with_services(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None,
        itinerary_agent=None,
        memory_service=None,
        preference_service=None
    ):
        """处理用户请求，协调所有服务

        Args:
            user_input: 用户输入
            conversation_id: 会话 ID
            user_id: 用户 ID
            itinerary_agent: 行程代理服务
            memory_service: 记忆服务
            preference_service: 偏好服务

        Yields:
            str: 流式响应片段
        """
        # 注册服务
        self.register_services(itinerary_agent, memory_service, preference_service)

        # 使用 QueryEngine 的处理流程
        async for chunk in self.process(user_input, conversation_id, user_id):
            yield chunk


# 全局集成引擎实例
_integrated_engine: Optional[IntegratedQueryEngine] = None


def get_integrated_engine() -> IntegratedQueryEngine:
    """获取全局集成 QueryEngine 实例"""
    global _integrated_engine
    if _integrated_engine is None:
        _integrated_engine = IntegratedQueryEngine()
        logger.info("[IntegratedQueryEngine] Created global integrated engine")
    return _integrated_engine
