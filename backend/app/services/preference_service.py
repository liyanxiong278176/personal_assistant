"""Preference extraction and storage service.

References:
- PERS-01: Store user preferences (budget, interests, style, travelers)
- D-07: Mixed approach - settings page explicit + AI conversation extraction
- 03-RESEARCH.md: LLM-based preference extraction with confirmation
"""

import json
import logging
import re
from typing import Optional

from app.db.postgres import get_preferences, update_preferences
# 使用新的 LLMClient 替代旧的 llm_service
from app.core.llm import LLMClient

logger = logging.getLogger(__name__)

# Global LLM client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


class PreferenceService:
    """Service for extracting and managing user preferences.

    Per D-07: Hybrid approach - explicit settings + AI extraction from conversation.
    """

    async def extract_preferences(
        self,
        conversation_text: str,
        current_preferences: Optional[dict] = None
    ) -> dict:
        """Extract user preferences from conversation using LLM.

        Per 03-RESEARCH.md: Extract with confidence scores for confirmation.

        Args:
            conversation_text: Recent conversation messages
            current_preferences: Existing preferences for context

        Returns:
            Extracted preferences with confidence score
        """
        # Build extraction prompt
        current_context = ""
        if current_preferences:
            current_context = f"\n当前已知偏好：{json.dumps(current_preferences, ensure_ascii=False)}"

        prompt = f"""从以下对话中提取用户的旅游偏好信息。

对话内容：
{conversation_text}
{current_context}

请提取以下字段（如果对话中未提及，保持为null或空数组）：
1. name: 用户姓名（如"张天"）
2. budget: 预算水平，值为 "low"（经济）、"medium"（中等）、"high"（豪华）
3. interests: 兴趣标签数组，如 ["历史", "美食", "自然", "购物", "艺术"]
4. style: 旅行风格，值为 "放松"（悠闲）、"紧凑"（充实）、"冒险"（探索）
5. travelers: 出行人数（整数）
6. confidence: 置信度（0-1的浮点数），表示你对提取结果的确定程度

请以JSON格式返回，必须包含以上6个字段。
示例格式：
{{"name": "张天", "budget": "medium", "interests": ["历史", "美食"], "style": "放松", "travelers": 2, "confidence": 0.8}}
"""

        try:
            # Call LLM for extraction using LLMClient
            llm_client = get_llm_client()
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是一个专业的旅游偏好提取助手。"
            )

            # Parse JSON response
            extracted = self._parse_extraction_response(response)

            logger.info(f"[PreferenceService] Extracted preferences: {extracted}")
            return extracted

        except Exception as e:
            logger.error(f"[PreferenceService] Extraction failed: {e}")
            # Return empty extraction on failure
            return {
                "budget": None,
                "interests": [],
                "style": None,
                "travelers": 1,
                "confidence": 0.0
            }

    def _parse_extraction_response(self, response: str) -> dict:
        """Parse LLM response into preference dict.

        Args:
            response: LLM response text

        Returns:
            Parsed preferences dict
        """
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*"confidence"[^{}]*\}', response, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{[^{}]*"budget"[^{}]*\}', response, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{[^{}]*"name"[^{}]*\}', response, re.DOTALL)

        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Ensure required fields exist
                return {
                    "name": parsed.get("name"),
                    "budget": parsed.get("budget"),
                    "interests": parsed.get("interests", []),
                    "style": parsed.get("style"),
                    "travelers": parsed.get("travelers", 1),
                    "confidence": parsed.get("confidence", 0.5)
                }
            except json.JSONDecodeError:
                pass

        # Fallback
        return {
            "name": None,
            "budget": None,
            "interests": [],
            "style": None,
            "travelers": 1,
            "confidence": 0.0
        }

    async def sync_preferences(
        self,
        user_id: str,
        extracted: dict,
        auto_confirm: bool = False
    ) -> dict:
        """Sync extracted preferences to database.

        Per 03-RESEARCH.md: Ask for confirmation if confidence < 0.7

        Args:
            user_id: User identifier
            extracted: Extracted preferences with confidence
            auto_confirm: If True, skip confirmation check

        Returns:
            Sync result with status
        """
        confidence = extracted.get("confidence", 0.0)
        preferences_to_update = {
            k: v for k, v in extracted.items()
            if k not in ("confidence") and v is not None
        }

        # Check if confirmation needed (per 03-RESEARCH.md)
        if not auto_confirm and confidence < 0.7:
            logger.info(f"[PreferenceService] Low confidence ({confidence}), requesting confirmation")
            return {
                "status": "needs_confirmation",
                "extracted": extracted,
                "message": "我从对话中了解到这些偏好，请确认是否正确"
            }

        # Auto-update for high confidence or explicit confirmation
        await update_preferences(user_id, preferences_to_update)
        logger.info(f"[PreferenceService] Updated preferences for user={user_id}")

        return {
            "status": "updated",
            "preferences": preferences_to_update
        }

    async def get_or_extract(
        self,
        user_id: str,
        conversation_text: Optional[str] = None
    ) -> dict:
        """Get existing preferences or extract from conversation.

        Args:
            user_id: User identifier
            conversation_text: Optional conversation text for extraction

        Returns:
            Current preferences (possibly updated from conversation)
        """
        # Get current preferences
        current = await get_preferences(user_id)
        if current is None:
            current = {"name": None, "budget": None, "interests": [], "style": None, "travelers": 1}

        # Extract from conversation if provided
        if conversation_text:
            extracted = await self.extract_preferences(conversation_text, current)
            # Only sync if confidence is good
            if extracted.get("confidence", 0) >= 0.7:
                result = await self.sync_preferences(user_id, extracted, auto_confirm=True)
                if result["status"] == "updated":
                    current.update(result["preferences"])

        return current


# Global service instance
preference_service = PreferenceService()
