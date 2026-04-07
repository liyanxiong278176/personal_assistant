"""PromptService - Orchestrates prompt template rendering with pipeline processing

Provides:
- Template retrieval from provider
- Variable injection (slots, memories, tool_results, user_message)
- Filter pipeline (security, validator, compressor)
- Safe rendering with error handling

Example:
    service = PromptService(
        provider=TemplateProvider(),
        filters=[SecurityFilter(), Validator()],
        enable_security_filter=True,
        enable_compressor=True
    )
    result = await service.render_safe("itinerary", context)
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.core.prompts.providers.base import IPromptProvider, PromptFilterResult
from app.core.prompts.pipeline.base import IPromptFilter
from app.core.prompts.pipeline.security import SecurityFilter
from app.core.prompts.pipeline.compressor import TokenCompressor

if TYPE_CHECKING:
    from app.core.context import RequestContext
    from app.core.intent.slot_extractor import SlotResult

logger = logging.getLogger(__name__)


class PromptService:
    """Prompt service - orchestrates prompt rendering with filter pipeline

    The service follows this flow:
    1. Get template from provider by intent
    2. Inject variables (user_message, slots, memories, tool_results)
    3. Apply filter pipeline (security, validator, compressor)
    4. Return final prompt

    Filters are applied in order:
    - SecurityFilter: Detects injection attacks
    - Validator: Ensures required variables are present
    - TokenCompressor: Ensures token budget is respected
    """

    def __init__(
        self,
        provider: IPromptProvider,
        filters: Optional[List[IPromptFilter]] = None,
        enable_security_filter: bool = True,
        enable_compressor: bool = True,
    ):
        """Initialize prompt service

        Args:
            provider: Template provider for retrieving prompts
            filters: Optional list of additional filters (applied after security, before compressor)
            enable_security_filter: Whether to enable built-in security filter
            enable_compressor: Whether to enable built-in token compressor
        """
        self.provider = provider
        self._filters: List[IPromptFilter] = []

        # Add built-in security filter
        if enable_security_filter:
            self._filters.append(SecurityFilter())

        # Add custom filters
        if filters:
            self._filters.extend(filters)

        # Add built-in compressor last
        if enable_compressor:
            self._filters.append(TokenCompressor())

        logger.info(
            f"[PromptService] Initialized with {len(self._filters)} filters "
            f"(security={enable_security_filter}, compressor={enable_compressor})"
        )

    def add_filter(self, filter_obj: IPromptFilter) -> None:
        """Add a filter to the pipeline

        Filters are added before the compressor but after security.

        Args:
            filter_obj: Filter to add
        """
        # Insert before compressor (last filter)
        if self._filters and isinstance(self._filters[-1], TokenCompressor):
            self._filters.insert(-1, filter_obj)
        else:
            self._filters.append(filter_obj)
        logger.debug(f"[PromptService] Added filter: {filter_obj.__class__.__name__}")

    async def render(
        self,
        intent: str,
        context: "RequestContext",
    ) -> str:
        """Render prompt for intent with context

        Args:
            intent: Intent identifier (e.g., "itinerary", "query")
            context: Request context with slots, memories, etc.

        Returns:
            Rendered prompt string

        Raises:
            KeyError: If template not found
            ValueError: If variable injection fails
        """
        # 1. Get template
        template = await self.provider.get_template(intent)
        logger.debug(f"[PromptService] Got template for intent '{intent}'")

        # 2. Inject variables
        rendered = self._inject_variables(template.template, context)
        logger.debug(f"[PromptService] Injected variables, length={len(rendered)}")

        # 3. Apply filter pipeline
        for filter_obj in self._filters:
            result = await filter_obj.process(rendered, context)
            if not result.success:
                raise ValueError(f"Filter {filter_obj.__class__.__name__} failed: {result.error}")
            if result.warning:
                logger.warning(f"[PromptService] Filter warning: {result.warning}")
            rendered = result.content

        return rendered

    async def render_safe(
        self,
        intent: str,
        context: "RequestContext",
    ) -> PromptFilterResult:
        """Render prompt with error handling

        Unlike render(), this method catches exceptions and returns
        a PromptFilterResult with appropriate error information.

        Args:
            intent: Intent identifier
            context: Request context

        Returns:
            PromptFilterResult with rendered content or error details
        """
        try:
            content = await self.render(intent, context)
            return PromptFilterResult(success=True, content=content)
        except KeyError as e:
            logger.error(f"[PromptService] Template not found: {e}")
            return PromptFilterResult(
                success=False,
                content="",
                error=f"Template not found for intent '{intent}': {e}",
                should_fallback=True,
            )
        except ValueError as e:
            logger.error(f"[PromptService] Rendering failed: {e}")
            return PromptFilterResult(
                success=False,
                content="",
                error=str(e),
                should_fallback=True,
            )
        except Exception as e:
            logger.exception(f"[PromptService] Unexpected error: {e}")
            return PromptFilterResult(
                success=False,
                content="",
                error=f"Unexpected error: {e}",
                should_fallback=True,
            )

    def _inject_variables(
        self,
        template: str,
        context: "RequestContext",
    ) -> str:
        """Inject variables into template

        Supported variables:
        - {user_message}: The original user message
        - {slots}: Formatted slot extraction results
        - {memories}: Formatted memory items
        - {tool_results}: Formatted tool execution results

        Args:
            template: Template string with variable placeholders
            context: Request context with variable data

        Returns:
            Template with variables replaced
        """
        result = template

        # Inject user message (always required)
        result = result.replace("{user_message}", context.message)

        # Inject slots (always replace, even if empty)
        if "{slots}" in result:
            slots_content = self._format_slots(context.slots) if context.slots else "未提取到槽位信息"
            result = result.replace("{slots}", slots_content)

        # Inject memories (always replace, even if empty)
        if "{memories}" in result:
            memories_content = self._format_memories(context.memories) if context.memories else "无相关记忆"
            result = result.replace("{memories}", memories_content)

        # Inject tool results (always replace, even if empty)
        if "{tool_results}" in result:
            results_content = self._format_tool_results(context.tool_results) if context.tool_results else "无工具调用结果"
            result = result.replace("{tool_results}", results_content)

        return result

    def _format_slots(self, slots: "SlotResult") -> str:
        """Format SlotResult as string

        Args:
            slots: Slot extraction result

        Returns:
            Formatted string representation
        """
        parts = []
        if hasattr(slots, "destination") and slots.destination:
            parts.append(f"目的地: {slots.destination}")
        if hasattr(slots, "destinations") and slots.destinations:
            parts.append(f"目的地: {', '.join(slots.destinations)}")
        if hasattr(slots, "start_date") and slots.start_date:
            parts.append(f"开始日期: {slots.start_date}")
        if hasattr(slots, "end_date") and slots.end_date:
            parts.append(f"结束日期: {slots.end_date}")
        if hasattr(slots, "days") and slots.days:
            parts.append(f"天数: {slots.days}")
        if hasattr(slots, "travelers") and slots.travelers:
            parts.append(f"人数: {slots.travelers}人")
        if hasattr(slots, "budget") and slots.budget:
            parts.append(f"预算档次: {slots.budget}")
        if hasattr(slots, "budget_amount") and slots.budget_amount:
            parts.append(f"预算金额: {slots.budget_amount}元")
        if hasattr(slots, "need_hotel") and slots.need_hotel:
            parts.append("需要酒店: 是")
        if hasattr(slots, "need_weather") and slots.need_weather:
            parts.append("需要天气: 是")
        if hasattr(slots, "need_route") and slots.need_route:
            parts.append("需要路线规划: 是")
        if hasattr(slots, "need_food") and slots.need_food:
            parts.append("需要美食推荐: 是")
        if hasattr(slots, "interests") and slots.interests:
            parts.append(f"兴趣: {', '.join(slots.interests)}")

        return "\n".join(parts) if parts else "未提取到槽位信息"

    def _format_memories(self, memories: List[Any]) -> str:
        """Format memories list as string

        Args:
            memories: List of memory items

        Returns:
            Formatted string representation
        """
        if not memories:
            return "无相关记忆"

        parts = []
        for i, memory in enumerate(memories[:10], 1):  # Limit to 10 memories
            if isinstance(memory, dict):
                content = memory.get("content", str(memory))
            elif hasattr(memory, "content"):
                content = memory.content
            else:
                content = str(memory)
            parts.append(f"{i}. {content}")

        return "\n".join(parts) if parts else "无相关记忆"

    def _format_tool_results(self, results: Dict[str, Any]) -> str:
        """Format tool results as string

        Args:
            results: Dictionary of tool name to result

        Returns:
            Formatted string representation
        """
        if not results:
            return "无工具调用结果"

        parts = []
        for tool_name, result in results.items():
            if isinstance(result, dict):
                result_str = ", ".join(f"{k}={v}" for k, v in result.items())
            elif isinstance(result, str):
                result_str = result
            else:
                result_str = str(result)
            parts.append(f"{tool_name}: {result_str}")

        return "\n".join(parts) if parts else "无工具调用结果"
