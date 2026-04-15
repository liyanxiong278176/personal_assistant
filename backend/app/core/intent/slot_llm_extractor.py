"""LLMSlotExtractor - Function Calling based slot extraction.

Uses LLM Function Calling to extract travel slots from user messages.
Designed as Stage 2 after rule-based pre-extraction.
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.llm.client import LLMClient, ToolCall

from app.core.intent.slot_extractor import SlotResult

logger = logging.getLogger(__name__)


SLOT_TOOL_DEFINITION = {
    "name": "extract_travel_slots",
    "description": "从用户旅行相关消息中提取结构化参数",
    "parameters": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "目的地城市，如：北京、上海、三亚",
            },
            "destinations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "多目的地列表",
            },
            "start_date": {
                "type": "string",
                "description": "出发日期，格式 YYYY-MM-DD",
            },
            "end_date": {
                "type": "string",
                "description": "返回日期，格式 YYYY-MM-DD",
            },
            "days": {
                "type": "integer",
                "description": "行程天数",
            },
            "travelers": {
                "type": "integer",
                "description": "出行人数（含儿童）",
            },
            "budget_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "预算档次",
            },
            "budget_amount": {
                "type": "integer",
                "description": "具体预算金额（元）",
            },
            "interests": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["history", "food", "nature", "shopping", "art", "entertainment", "beach", "nightlife"],
                },
                "description": "兴趣标签",
            },
        },
        "required": [],
    },
}


class LLMSlotExtractor:
    """LLM Function Calling slot extractor.

    Used as Stage 2 after rule-based pre-extraction.
    Merge strategy: rule results take priority (already validated),
    LLM fills missing slots.
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "deepseek-chat",
        timeout: float = 10.0,
    ):
        """Initialize the LLM slot extractor.

        Args:
            llm_client: LLM client with chat_with_tools support
            model: Model name to use
            timeout: Request timeout in seconds
        """
        self._llm_client = llm_client
        self._model = model
        self._timeout = timeout

    async def extract(
        self,
        message: str,
        pre_extracted: Optional[SlotResult] = None,
    ) -> SlotResult:
        """Extract slots using Function Calling.

        Args:
            message: User message
            pre_extracted: Rule-based pre-extraction result

        Returns:
            Merged SlotResult (rule priority, LLM fills missing)
        """
        system_prompt = self._build_system_prompt(pre_extracted)

        try:
            content, tool_calls = await self._llm_client.chat_with_tools(
                messages=[{"role": "user", "content": message}],
                tools=[SLOT_TOOL_DEFINITION],
                system_prompt=system_prompt,
            )

            if tool_calls:
                llm_result = self._parse_tool_call(tool_calls[0])

                # Merge: rule first, LLM fills missing
                if pre_extracted:
                    merged = self._merge_results(pre_extracted, llm_result)
                    logger.info(
                        f"[LLMSlotExtractor] Merged | "
                        f"rule_dest={pre_extracted.destination} → "
                        f"final_dest={merged.destination}"
                    )
                    return merged
                return llm_result

            # No tool call: return pre-extracted
            logger.warning("[LLMSlotExtractor] No tool call, returning rule result")
            return pre_extracted or SlotResult()

        except Exception as e:
            logger.error(f"[LLMSlotExtractor] Error: {e}")
            return pre_extracted or SlotResult()

    def _build_system_prompt(self, pre: Optional[SlotResult]) -> str:
        """Build system prompt with context."""
        base = "你是旅行助手槽位提取专家。分析用户消息，调用 extract_travel_slots 工具提取参数。"

        if pre and self._has_slots(pre):
            existing = self._format_existing(pre)
            base += f"\n\n已有规则提取：{existing}\n请验证并补充缺失槽位。"

        return base

    def _has_slots(self, result: SlotResult) -> bool:
        """Check if result has any extracted slots."""
        return any([
            result.destination,
            result.destinations,
            result.days,
            result.start_date,
            result.travelers,
        ])

    def _format_existing(self, result: SlotResult) -> str:
        """Format existing slots for context."""
        parts = []
        if result.destination:
            parts.append(f"目的地={result.destination}")
        if result.days:
            parts.append(f"天数={result.days}")
        if result.travelers:
            parts.append(f"人数={result.travelers}")
        return ", ".join(parts) if parts else "无"

    def _parse_tool_call(self, call: "ToolCall") -> SlotResult:
        """Parse ToolCall arguments into SlotResult."""
        args = call.arguments if hasattr(call, 'arguments') else {}

        return SlotResult(
            destination=args.get("destination"),
            destinations=args.get("destinations"),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            days=args.get("days"),
            travelers=args.get("travelers"),
            budget=args.get("budget_level"),
            budget_amount=args.get("budget_amount"),
            interests=args.get("interests"),
        )

    def _merge_results(
        self,
        rule: SlotResult,
        llm: SlotResult
    ) -> SlotResult:
        """Merge: rule priority (validated), LLM fills missing."""
        merged = SlotResult()

        # Rule first (already validated patterns)
        merged.destination = rule.destination or llm.destination
        merged.destinations = rule.destinations or llm.destinations
        merged.days = rule.days or llm.days
        merged.start_date = rule.start_date or llm.start_date
        merged.end_date = rule.end_date or llm.end_date
        merged.travelers = rule.travelers or llm.travelers

        # LLM fills what rules can't extract
        merged.budget = rule.budget or llm.budget
        merged.budget_amount = rule.budget_amount or llm.budget_amount
        merged.interests = llm.interests or rule.interests

        return merged
