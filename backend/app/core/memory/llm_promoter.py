"""LLM-based memory importance evaluation with cost control."""
import asyncio
import logging
import re
from typing import Optional

from app.core.memory.hierarchy import MemoryType

logger = logging.getLogger(__name__)

# Few-shot examples for stable evaluation
IMPORTANCE_FEW_SHOT = """
你是一个记忆重要性评估专家。根据用户陈述，判断其长期记忆价值（0.0-1.0）。

评分标准：
- 0.0-0.3: 临时信息（问候、闲聊、一次性查询）
- 0.4-0.6: 中期信息（当前对话上下文、短期计划）
- 0.7-1.0: 长期信息（用户偏好、约束条件、核心事实）

示例：
用户输入: "你好"
评分: 0.1

���户输入: "帮我查一下明天天气"
评分: 0.2

用户输入: "我预算5000元计划去北京旅游"
评分: 0.8

用户输入: "我不喜欢人多的景点"
评分: 0.85

用户输入: {user_input}
评分："""


class LLMMemoryPromoter:
    """LLM-based memory importance evaluation with two-stage filtering."""

    def __init__(
        self,
        llm_client,
        rule_threshold: float = 0.5,
        llm_threshold: float = 0.7,
        timeout: float = 3.0,
    ):
        """Initialize LLM promoter.

        Args:
            llm_client: LLM client with async generate() method
            rule_threshold: Threshold for rule filtering (skip LLM if below)
            llm_threshold: Minimum LLM score to consider important
            timeout: LLM evaluation timeout in seconds
        """
        self._llm = llm_client
        self._rule_threshold = rule_threshold
        self._llm_threshold = llm_threshold
        self._timeout = timeout

    async def evaluate_importance(
        self,
        content: str,
        memory_type: Optional[MemoryType],
        rule_score: float,
    ) -> float:
        """Two-stage evaluation: rule filter + LLM assessment.

        Args:
            content: Memory content to evaluate
            memory_type: Type of memory (can be None)
            rule_score: Pre-calculated rule-based score

        Returns:
            Final importance score (0.0 to 1.0)
        """
        # Stage 1: Rule fast filtering
        if rule_score < self._rule_threshold:
            logger.debug(
                f"[LLMPromoter] Rule filtered: {rule_score:.2f} < {self._rule_threshold}"
            )
            return rule_score

        # Stage 2: LLM precise evaluation
        try:
            llm_score = await asyncio.wait_for(
                self._llm_evaluate(content),
                timeout=self._timeout
            )
            # Weighted fusion: rule 30% + LLM 70%
            final_score = rule_score * 0.3 + llm_score * 0.7

            logger.info(
                f"[LLMPromoter] LLM evaluated: rule={rule_score:.2f}, "
                f"llm={llm_score:.2f}, final={final_score:.2f}"
            )
            return final_score

        except asyncio.TimeoutError:
            logger.warning(f"[LLMPromoter] LLM timeout after {self._timeout}s")
            return rule_score  # Fallback to rule score
        except Exception as e:
            logger.warning(f"[LLMPromoter] LLM evaluation failed: {e}")
            return rule_score

    async def _llm_evaluate(self, content: str) -> float:
        """Evaluate importance using LLM.

        Args:
            content: Content to evaluate

        Returns:
            Importance score (0.0 to 1.0)
        """
        prompt = IMPORTANCE_FEW_SHOT.format(user_input=content)

        response = await self._llm.generate(prompt)

        # Extract numeric score from response
        match = re.search(r'0\.\d+|1\.0|0\.0', response)
        if match:
            return float(match.group())

        logger.warning(f"[LLMPromoter] Could not parse score from: {response[:50]}")
        return 0.5  # Neutral fallback
