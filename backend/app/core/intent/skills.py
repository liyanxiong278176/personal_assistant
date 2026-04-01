"""Skill Trigger System

Provides pattern-based action triggers that work alongside slash commands.
Skills are the second layer of intent routing, activated after slash commands.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, List, Dict, Any

from app.core.errors import AgentError

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """Result of a skill match and execution.

    Attributes:
        skill_name: Name of the matched skill
        confidence: Confidence score of the match (0.0 to 1.0)
        matched_text: The text that matched the pattern
        message: Response message to display to the user
        data: Optional additional data (e.g., structured results)
        error: Optional error message if execution failed
        success: Whether the skill executed successfully
    """
    skill_name: str
    confidence: float
    matched_text: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    success: bool = True

    def __str__(self) -> str:
        """Return the message as string representation."""
        return self.message


class Skill:
    """Skill definition with pattern matching.

    A skill represents a capability that can be triggered by natural
    language patterns rather than explicit slash commands.

    Example:
        ```python
        async def handle_itinerary(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="itinerary_planning",
                confidence=1.0,
                matched_text=input_text,
                message="I'll help you plan your itinerary!"
            )

        skill = Skill(
            name="itinerary_planning",
            patterns=[r"规划.*行程", r"制定.*计划"],
            handler=handle_itinerary,
            description="Plan travel itineraries"
        )
        ```
    """

    def __init__(
        self,
        name: str,
        patterns: List[str],
        handler: Callable[..., Awaitable[SkillResult]],
        description: str
    ):
        """Initialize a Skill.

        Args:
            name: Skill name (identifier)
            patterns: List of regex patterns to match input text
            handler: Async function that returns SkillResult
            description: Human-readable description of the skill
        """
        self.name = name
        self._raw_patterns = patterns
        self._compiled_patterns = [re.compile(pattern) for pattern in patterns]
        self.handler = handler
        self.description = description

    def match(
        self,
        input_text: str,
        confidence: float = 0.7
    ) -> Optional[SkillResult]:
        """Check if input text matches this skill's patterns.

        Args:
            input_text: User input text to match against
            confidence: Minimum confidence threshold (0.0 to 1.0)

        Returns:
            SkillResult if matched with sufficient confidence, None otherwise
        """
        input_text = input_text.strip()

        for pattern in self._compiled_patterns:
            match = pattern.search(input_text)
            if match:
                matched_text = match.group(0)
                # Calculate confidence based on match specificity
                # Longer, more specific matches get higher confidence
                match_confidence = min(1.0, len(matched_text) / len(input_text) + 0.5)

                if match_confidence >= confidence:
                    return SkillResult(
                        skill_name=self.name,
                        confidence=match_confidence,
                        matched_text=matched_text,
                        message="",  # Will be filled by execute()
                        success=True
                    )

        return None

    async def execute(
        self,
        input_text: str,
        **kwargs
    ) -> SkillResult:
        """Execute the skill with the given input.

        Args:
            input_text: The user's input text
            **kwargs: Additional context (conversation_id, user_id, etc.)

        Returns:
            SkillResult with the execution outcome

        Raises:
            AgentError: If skill execution fails
        """
        try:
            result = await self.handler(
                input_text=input_text,
                **kwargs
            )

            if not isinstance(result, SkillResult):
                logger.warning(
                    f"[Skill] Handler for '{self.name}' "
                    f"returned non-SkillResult: {type(result)}"
                )
                # Convert to SkillResult if possible
                if isinstance(result, str):
                    result = SkillResult(
                        skill_name=self.name,
                        confidence=1.0,
                        matched_text=input_text,
                        message=result,
                        success=True
                    )
                else:
                    raise AgentError(
                        f"Skill handler returned invalid type: {type(result)}"
                    )

            return result

        except AgentError:
            raise
        except Exception as e:
            logger.error(f"[Skill] Execution failed for '{self.name}': {e}")
            raise AgentError(f"Skill execution failed: {e}")


class SkillRegistry:
    """Registry for managing skills.

    The registry maintains a collection of skills and provides
    methods for registration, matching, and listing.

    Example:
        ```python
        registry = SkillRegistry()

        registry.register(Skill(
            name="itinerary_planning",
            patterns=[r"规划.*行程"],
            handler=handle_itinerary,
            description="Plan itineraries"
        ))

        skill_result = registry.match("请帮我规划北京行程")
        if skill_result:
            result = await skill_result.skill.execute("请帮我规划北京行程")
        ```
    """

    def __init__(self):
        """Initialize an empty SkillRegistry."""
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill.

        Args:
            skill: Skill instance to register

        Raises:
            ValueError: If a skill with the same name already exists
        """
        if skill.name in self._skills:
            raise ValueError(
                f"Skill '{skill.name}' is already registered. "
                f"Use replace() to override."
            )

        self._skills[skill.name] = skill
        logger.info(f"[SkillRegistry] Registered skill: {skill.name}")

    def replace(self, skill: Skill) -> None:
        """Replace an existing skill or register if new.

        Args:
            skill: Skill instance to register/replace
        """
        if skill.name in self._skills:
            logger.info(f"[SkillRegistry] Replacing skill: {skill.name}")
        else:
            logger.info(f"[SkillRegistry] Registering skill: {skill.name}")

        self._skills[skill.name] = skill

    def unregister(self, name: str) -> bool:
        """Unregister a skill.

        Args:
            name: Skill name to unregister

        Returns:
            True if skill was removed, False if not found
        """
        if name in self._skills:
            del self._skills[name]
            logger.info(f"[SkillRegistry] Unregistered skill: {name}")
            return True
        return False

    def match(
        self,
        input_text: str,
        confidence: float = 0.7
    ) -> Optional[SkillResult]:
        """Find a skill that matches the input text.

        Args:
            input_text: User input text to match
            confidence: Minimum confidence threshold (0.0 to 1.0)

        Returns:
            SkillResult if matched with sufficient confidence, None otherwise

        Note:
            Returns the first matching skill. If multiple skills match,
            the one with the highest confidence is returned.
        """
        best_match: Optional[SkillResult] = None

        for skill in self._skills.values():
            result = skill.match(input_text, confidence)
            if result:
                if best_match is None or result.confidence > best_match.confidence:
                    best_match = result

        return best_match

    async def execute_match(
        self,
        input_text: str,
        confidence: float = 0.7,
        **kwargs
    ) -> Optional[SkillResult]:
        """Match and execute a skill for the given input.

        Args:
            input_text: User input text
            confidence: Minimum confidence threshold
            **kwargs: Additional context (conversation_id, user_id, etc.)

        Returns:
            SkillResult after execution, or None if no match
        """
        match_result = self.match(input_text, confidence)
        if match_result:
            skill = self._skills.get(match_result.skill_name)
            if skill:
                return await skill.execute(input_text, **kwargs)

        return None

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill if found, None otherwise
        """
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """List all registered skill names.

        Returns:
            List of skill names sorted alphabetically
        """
        return sorted(self._skills.keys())

    def list_skills_details(self) -> List[Dict[str, str]]:
        """List all registered skills with details.

        Returns:
            List of dicts with 'name', 'description', and 'patterns' keys
        """
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "patterns": skill._raw_patterns
            }
            for skill in sorted(self._skills.values(), key=lambda s: s.name)
        ]

    @property
    def skills(self) -> Dict[str, Skill]:
        """Get all registered skills."""
        return self._skills.copy()

    def __len__(self) -> int:
        """Return the number of registered skills."""
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        """Check if a skill is registered."""
        return name in self._skills


# Global registry instance
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry.

    Creates the registry on first call and registers default skills.

    Returns:
        The global SkillRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
        _register_default_skills(_global_registry)
        logger.info("[SkillRegistry] Created global registry with defaults")
    return _global_registry


def set_skill_registry(registry: SkillRegistry) -> None:
    """Set a custom global skill registry.

    Args:
        registry: SkillRegistry to use as global
    """
    global _global_registry
    _global_registry = registry
    logger.info("[SkillRegistry] Set custom global registry")


def _register_default_skills(registry: SkillRegistry) -> None:
    """Register default skills.

    Args:
        registry: The registry to register skills into
    """

    # itinerary_planning - 行程规划
    async def handle_itinerary_planning(
        input_text: str,
        **kwargs
    ) -> SkillResult:
        # Extract destination if mentioned
        destination = None
        common_cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆",
                        "Beijing", "Shanghai", "Guangzhou", "Shenzhen", "Hangzhou",
                        "Chengdu", "Xian", "Chongqing", "Tokyo", "Paris", "London"]
        for city in common_cities:
            if city in input_text:
                destination = city
                break

        if destination:
            message = f"我来帮您规划{destination}的行程！请告诉我您的旅行日期、偏好和预算。"
        else:
            message = "我来帮您规划行程！请告诉我您想去哪里，以及您的旅行日期和偏好。"

        return SkillResult(
            skill_name="itinerary_planning",
            confidence=1.0,
            matched_text=input_text,
            message=message,
            data={"action": "itinerary_planning", "destination": destination},
            success=True
        )

    registry.register(Skill(
        name="itinerary_planning",
        patterns=[
            r"规划.*行程",
            r"制定.*计划",
            r"安排.*旅游",
            r"设计.*路线",
            r"计划.*旅行",
            r"行程.*规划",
        ],
        handler=handle_itinerary_planning,
        description="行程规划 - 帮助用户制定旅行计划"
    ))

    # attraction_recommendation - 景点推荐
    async def handle_attraction_recommendation(
        input_text: str,
        **kwargs
    ) -> SkillResult:
        # Try to extract destination
        destination = None
        common_cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆",
                        "Beijing", "Shanghai", "Guangzhou", "Shenzhen", "Hangzhou",
                        "Chengdu", "Xian", "Chongqing", "Tokyo", "Paris", "London"]
        for city in common_cities:
            if city in input_text:
                destination = city
                break

        if destination:
            message = f"为您推荐{destination}的热门景点！让我查找一下最受欢迎的地方..."
        else:
            message = "我很乐意为您推荐景点！请告诉我您想去哪个城市或地区？"

        return SkillResult(
            skill_name="attraction_recommendation",
            confidence=1.0,
            matched_text=input_text,
            message=message,
            data={"action": "attraction_recommendation", "destination": destination},
            success=True
        )

    registry.register(Skill(
        name="attraction_recommendation",
        patterns=[
            r"推荐.*景点",
            r"哪里.*好玩",
            r"有什么.*景点",
            r"必去.*地方",
            r"值得一去",
            r"景点.*推荐",
            r"好玩.*地方",
            r"旅游.*胜地",
        ],
        handler=handle_attraction_recommendation,
        description="景点推荐 - 推荐热门旅游景点"
    ))

    # travel_advice - 旅行建议
    async def handle_travel_advice(
        input_text: str,
        **kwargs
    ) -> SkillResult:
        # Detect if asking about transportation
        transport_keywords = ["交通", "怎么去", "如何到达", "坐飞机", "坐高铁", "坐火车",
                            "transport", "how to get", "flight", "train"]
        is_transport = any(kw in input_text for kw in transport_keywords)

        if is_transport:
            message = "关于交通方式，我可以帮您查询最佳的出行方案。请告诉我您的出发地和目的地！"
        else:
            message = "我很乐意为您提供旅行建议！请告诉我您想了解哪方面的信息（交通、住宿、注意事项等）"

        return SkillResult(
            skill_name="travel_advice",
            confidence=1.0,
            matched_text=input_text,
            message=message,
            data={"action": "travel_advice", "is_transport_query": is_transport},
            success=True
        )

    registry.register(Skill(
        name="travel_advice",
        patterns=[
            r"建议.*交通",
            r"怎么.*去",
            r"注意.*事项",
            r"如何.*到达",
            r"出行.*建议",
            r"交通.*方式",
            r"旅行.*攻略",
            r"旅游.*贴士",
        ],
        handler=handle_travel_advice,
        description="旅行建议 - 提供交通、注意事项等建议"
    ))


__all__ = [
    "SkillResult",
    "Skill",
    "SkillRegistry",
    "get_skill_registry",
    "set_skill_registry",
]
