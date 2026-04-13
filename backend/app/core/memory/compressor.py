"""Multi-level conversation compression with configurable slot templates."""
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Pattern

logger = logging.getLogger(__name__)


@dataclass
class SlotExtractionTemplate:
    """Slot extraction template (configurable).

    This is the single source of truth for slot templates.
    Task 5 (config.py) imports this from here.
    """
    name: str
    pattern: str
    label: str
    flags: int = 0

    def compile(self) -> Pattern:
        return re.compile(self.pattern, self.flags)


# Preset templates for travel scenarios
TRAVEL_TEMPLATES = [
    SlotExtractionTemplate("destination", r'(北京|上海|东京|巴黎|\w{2,4}国)', "目的地"),
    SlotExtractionTemplate("date", r'(\d+月\d+日|\d+/\d+)', "时间"),
    SlotExtractionTemplate("budget", r'(\d+)元', "预算"),
    SlotExtractionTemplate("days", r'(\d+)天', "天数"),
]

# Preset templates for generic scenarios
GENERIC_TEMPLATES = [
    SlotExtractionTemplate("number", r'\b(\d+(?:\.\d+)?)\b', "数字"),
    SlotExtractionTemplate("email", r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', "邮箱"),
]


class ConversationCompressor:
    """Multi-level conversation compressor.

    Compression levels:
    - Recent (last 5): Full preservation
    - Mid (5-20): Slot extraction using configured templates
    - Old (20+): LLM summarization
    """

    def __init__(
        self,
        llm_client,
        llm_timeout: float = 5.0,
        slot_templates: Optional[List[SlotExtractionTemplate]] = None,
        recent_limit: int = 5,
        mid_limit: int = 20,
    ):
        """Initialize compressor.

        Args:
            llm_client: LLM client for summarization
            llm_timeout: Timeout for LLM calls
            slot_templates: Optional custom templates (defaults to travel)
            recent_limit: Number of recent messages to preserve fully
            mid_limit: Total messages before triggering LLM summary
        """
        self._llm = llm_client
        self._timeout = llm_timeout
        self._recent_limit = recent_limit
        self._mid_limit = mid_limit

        self._slot_templates = slot_templates or TRAVEL_TEMPLATES
        self._compiled_templates = [
            (t, t.compile()) for t in self._slot_templates
        ]

        logger.info(
            f"[Compressor] Initialized | recent={recent_limit} | mid={mid_limit} | "
            f"templates={len(self._slot_templates)}"
        )

    async def compress(self, messages: List[Dict]) -> List[Dict]:
        """Multi-level compression.

        Args:
            messages: List of message dicts with 'role' and 'content' keys

        Returns:
            Compressed message list with some messages replaced by slots/summary
        """
        if len(messages) <= self._recent_limit:
            return messages

        result = []

        # Level 1: Recent messages - full preservation
        recent = messages[-self._recent_limit:]
        result.extend(recent)

        # Level 2: Mid messages - slot extraction
        if len(messages) > self._recent_limit:
            mid_start = max(0, len(messages) - self._mid_limit)
            mid = messages[mid_start:-self._recent_limit]
            for msg in mid:
                compressed = self._extract_slots(msg["content"])
                if compressed:
                    result.append({
                        "role": msg["role"],
                        "content": compressed,
                        "_compressed": True
                    })

        # Level 3: Old messages - LLM summary
        if len(messages) > self._mid_limit:
            old = messages[:max(0, len(messages) - self._mid_limit)]
            if old:
                summary = await self._summarize(old)
                result.insert(0, {
                    "role": "system",
                    "content": f"[对话摘要] {summary}",
                    "_compressed": True
                })

        return result

    def _extract_slots(self, content: str) -> str:
        """Extract slots using configured templates."""
        slots = []

        for template, pattern in self._compiled_templates:
            match = pattern.search(content)
            if match:
                slots.append(f"{template.label}: {match.group(1)}")

        return " | ".join(slots) if slots else ""

    def set_slot_templates(self, templates: List[SlotExtractionTemplate]):
        """Dynamically update slot templates (supports scenario switching)."""
        self._slot_templates = templates
        self._compiled_templates = [
            (t, t.compile()) for t in templates
        ]
        logger.info(f"[Compressor] Updated {len(templates)} slot templates")

    async def _summarize(self, messages: List[Dict]) -> str:
        """LLM-based summarization of old messages."""
        # Only summarize the last 10 messages to reduce token usage
        conversation = "\n".join([
            f"{m['role']}: {m['content']}"
            for m in messages[-10:]
        ])

        prompt = f"""将以下对话摘要为1-2句话，保留关键信息：

{conversation}

摘要："""

        try:
            return await asyncio.wait_for(
                self._llm.chat(prompt),
                timeout=self._timeout
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"[Compressor] Summarization failed: {e}")
            return "（早期对话已压缩）"
