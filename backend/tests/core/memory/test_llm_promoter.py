import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.core.memory.llm_promoter import LLMMemoryPromoter
from app.core.memory.hierarchy import MemoryType


class TestLLMMemoryPromoter:
    """Tests for LLMMemoryPromoter."""

    @pytest.mark.asyncio
    async def test_rule_filtering_below_threshold(self):
        """Rule score below threshold should skip LLM call."""
        llm = AsyncMock()
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

        score = await promoter.evaluate_importance(
            "你好", MemoryType.STATE, rule_score=0.3
        )

        assert score == 0.3
        llm.generate.assert_not_awaited()  # LLM should not be called

    @pytest.mark.asyncio
    async def test_llm_evaluation_above_threshold(self):
        """Rule score above threshold should trigger LLM evaluation."""
        llm = AsyncMock()
        llm.generate.return_value = "0.8"
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

        score = await promoter.evaluate_importance(
            "我喜欢自然景观", MemoryType.PREFERENCE, rule_score=0.6
        )

        # 0.6 * 0.3 + 0.8 * 0.7 = 0.18 + 0.56 = 0.74
        assert abs(score - 0.74) < 0.01
        llm.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_timeout_fallback(self):
        """LLM timeout should fallback to rule score."""
        llm = AsyncMock()
        llm.generate.side_effect = asyncio.TimeoutError()

        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5, timeout=0.1)

        score = await promoter.evaluate_importance(
            "测试", MemoryType.FACT, rule_score=0.6
        )

        assert score == 0.6  # Should return rule score on timeout

    @pytest.mark.asyncio
    async def test_exception_fallback(self):
        """LLM exception should fallback to rule score."""
        llm = AsyncMock()
        llm.generate.side_effect = Exception("LLM failed")

        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

        score = await promoter.evaluate_importance(
            "测试", MemoryType.FACT, rule_score=0.6
        )

        assert score == 0.6  # Should return rule score on exception

    @pytest.mark.asyncio
    async def test_score_parsing(self):
        """LLM response should parse numeric score correctly."""
        llm = AsyncMock()
        llm.generate.return_value = "根据分析，这个信息的长期记忆价值为0.85分。"
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.3)

        score = await promoter.evaluate_importance(
            "我偏好安静的旅行方式", MemoryType.PREFERENCE, rule_score=0.5
        )

        assert abs(score - 0.745) < 0.01  # 0.5*0.3 + 0.85*0.7 = 0.745

    @pytest.mark.asyncio
    async def test_memory_type_none_handling(self):
        """Should handle None memory_type gracefully."""
        llm = AsyncMock()
        llm.generate.return_value = "0.9"
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.3)

        score = await promoter.evaluate_importance(
            "重要偏好", None, rule_score=0.5
        )

        assert abs(score - 0.78) < 0.01  # 0.5*0.3 + 0.9*0.7 = 0.78

    @pytest.mark.asyncio
    async def test_unparseable_llm_response_fallback(self):
        """Unparseable LLM response should use neutral fallback score."""
        llm = AsyncMock()
        llm.generate.return_value = "I cannot determine the importance."
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.3)

        score = await promoter.evaluate_importance(
            "测试内容", MemoryType.FACT, rule_score=0.5
        )

        # 0.5*0.3 + 0.5*0.7 = 0.5 (neutral fallback)
        assert abs(score - 0.5) < 0.01

    @pytest.mark.asyncio
    async def test_edge_case_exact_threshold(self):
        """Rule score exactly at threshold should still trigger LLM."""
        llm = AsyncMock()
        llm.generate.return_value = "0.75"
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

        score = await promoter.evaluate_importance(
            "测试", MemoryType.FACT, rule_score=0.5
        )

        # 0.5*0.3 + 0.75*0.7 = 0.675
        assert abs(score - 0.675) < 0.01
        llm.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_score_parsing_various_formats(self):
        """Should parse various numeric score formats."""
        llm = AsyncMock()
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.1)

        # Test 1.0 format
        llm.generate.return_value = "评分: 1.0"
        score = await promoter.evaluate_importance(
            "测试", MemoryType.PREFERENCE, rule_score=0.5
        )
        assert abs(score - 0.85) < 0.01  # 0.5*0.3 + 1.0*0.7

        # Test 0.0 format
        llm.generate.return_value = "评分: 0.0"
        score = await promoter.evaluate_importance(
            "测试", MemoryType.PREFERENCE, rule_score=0.5
        )
        assert abs(score - 0.15) < 0.01  # 0.5*0.3 + 0.0*0.7
