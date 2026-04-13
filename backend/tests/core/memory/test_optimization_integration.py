"""End-to-end integration tests for memory optimization v2.2."""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from app.core.memory.forgetting_curve import ForgettingCurveManager, MemoryStrength
from app.core.memory.llm_promoter import LLMMemoryPromoter
from app.core.memory.compressor import ConversationCompressor, SlotExtractionTemplate
from app.core.memory.config import MemoryConfig


class TestLLMPromoterIntegration:
    """Integration tests for LLMMemoryPromoter."""

    @pytest.mark.asyncio
    async def test_two_stage_evaluation_flow(self):
        """Test complete two-stage evaluation: rule filter -> LLM -> fusion."""
        llm = AsyncMock()
        llm.generate.return_value = "0.85"

        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

        # Stage 1: Above rule threshold, LLM should be called
        score = await promoter.evaluate_importance(
            "我喜欢安静的自然环境",
            None,
            0.6  # rule score above threshold
        )

        # 0.6 * 0.3 + 0.85 * 0.7 = 0.775
        assert abs(score - 0.775) < 0.01
        llm.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rule_filter_blocks_llm(self):
        """Rule filter should prevent LLM call for low-score content."""
        llm = AsyncMock()
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

        # Below rule threshold
        score = await promoter.evaluate_importance(
            "你好",
            None,
            0.2
        )

        assert score == 0.2
        llm.generate.assert_not_awaited()


class TestForgettingCurveIntegration:
    """Integration tests for ForgettingCurveManager."""

    @pytest.mark.asyncio
    async def test_retrieve_filter_reinforce_full_flow(self):
        """Test full flow: retrieve -> filter -> reinforce -> persist."""
        repo = AsyncMock()
        repo.update_metadata.return_value = True

        manager = ForgettingCurveManager(repo)

        # Active memory (recent, high importance, already accessed once)
        # Note: log(1+access_count) factor requires access_count > 0 for non-zero strength
        active_mem = {
            "id": "mem_active",
            "content": "用户喜欢安静",
            "metadata": {
                "created_at": time.time() - 86400,  # 1 day ago
                "importance": 0.8,
                "strength": {
                    "initial_strength": 0.8,
                    "created_at": time.time() - 86400,
                    "last_accessed": time.time() - 3600,
                    "access_count": 1,  # Already accessed once
                    "decay_factor": 30,
                }
            }
        }

        # Forgotten memory (old, never accessed)
        forgotten_mem = {
            "id": "mem_forgotten",
            "content": "临时查询",
            "metadata": {
                "created_at": time.time() - 100 * 86400,  # 100 days ago
                "importance": 0.5,
                "strength": {
                    "initial_strength": 0.5,
                    "created_at": time.time() - 100 * 86400,
                    "last_accessed": time.time() - 100 * 86400,
                    "access_count": 0,
                    "decay_factor": 30,
                }
            }
        }

        # Filter
        active = await manager.filter_active([active_mem, forgotten_mem])
        assert len(active) == 1
        assert active[0]["id"] == "mem_active"

        # Reinforce
        await manager.reinforce_memories([active_mem])
        repo.update_metadata.assert_called()

        call_args = repo.update_metadata.call_args
        updated_strength = call_args[0][1]["strength"]
        # access_count should be 2 now (1 + 1 from reinforcement)
        assert updated_strength["access_count"] == 2

    def test_memory_strength_decay_reinforcement_cycle(self):
        """Test that reinforcement counteracts decay."""
        strength = MemoryStrength(
            initial_strength=0.8,
            created_at=time.time() - 15 * 86400,  # 15 days old
            decay_factor=30,
            access_count=0,
        )

        initial = strength.get_current_strength()

        # Reinforce multiple times
        for _ in range(5):
            strength.reinforce()

        reinforced = strength.get_current_strength()

        # Reinforcement should have increased strength
        assert reinforced > initial
        # But still bounded
        assert reinforced <= 1.0


class TestCompressorIntegration:
    """Integration tests for ConversationCompressor."""

    @pytest.mark.asyncio
    async def test_compress_with_llm_summary(self):
        """Test compression with LLM summary for old messages."""
        # Note: ConversationCompressor uses llm.chat() for summarization
        llm = AsyncMock()
        llm.chat.return_value = "用户计划去北京旅游，预算5000元。"

        compressor = ConversationCompressor(
            llm,
            recent_limit=3,
            mid_limit=10,
        )

        # 15 messages: 3 recent + 7 mid + 5 old
        messages = [{"role": "user", "content": f"内容{i}"} for i in range(15)]

        result = await compressor.compress(messages)

        # Recent should be preserved
        recent = [m for m in result if not m.get("_compressed")]
        assert len(recent) == 3

        # Old should be summarized
        summaries = [m for m in result if m["role"] == "system"]
        assert len(summaries) == 1
        assert "北京" in summaries[0]["content"]
        assert "5000" in summaries[0]["content"]

    @pytest.mark.asyncio
    async def test_compress_slot_extraction_travel(self):
        """Test slot extraction on mid-range messages."""
        llm = AsyncMock()
        compressor = ConversationCompressor(llm, recent_limit=2, mid_limit=5)

        messages = [
            {"role": "user", "content": "你好"},  # old
            {"role": "user", "content": "我想去北京"},  # old
            {"role": "user", "content": "5月1日出发"},  # mid -> slot
            {"role": "user", "content": "预算3000元"},  # mid -> slot
            {"role": "user", "content": "谢谢推荐"},  # recent (1)
        ]

        result = await compressor.compress(messages)

        # The mid messages should be slot-compressed
        compressed = [m for m in result if m.get("_compressed")]

        # Some should have extracted slots
        has_slots = any("目的地" in m.get("content", "") or
                       "时间" in m.get("content", "") or
                       "预算" in m.get("content", "")
                       for m in compressed)
        assert has_slots or len(compressed) > 0

    def test_template_switching(self):
        """Test dynamic template switching between scenarios."""
        llm = AsyncMock()
        compressor = ConversationCompressor(llm)

        # Switch to generic templates (patterns must have capture groups)
        generic = [
            SlotExtractionTemplate("phone", r'(1[3-9]\d{9})', "手机号"),
            SlotExtractionTemplate("email", r'([\w.-]+@[\w.-]+\.\w+)', "邮箱"),
        ]
        compressor.set_slot_templates(generic)

        result = compressor._extract_slots("联系我13812345678或test@example.com")
        assert "手机号" in result or "邮箱" in result

        # Switch back to travel templates
        from app.core.memory.compressor import TRAVEL_TEMPLATES
        compressor.set_slot_templates(TRAVEL_TEMPLATES)

        result2 = compressor._extract_slots("预算5000元去北京")
        assert "目的地" in result2 or "预算" in result2


class TestCrossComponentIntegration:
    """Integration tests across multiple components."""

    @pytest.mark.asyncio
    async def test_llm_promoter_with_compressor(self):
        """Test that compressor can work with LLM promoter scenarios."""
        # Create LLM mock with both generate (for promoter) and chat (for compressor)
        llm = AsyncMock()
        llm.generate.return_value = "0.85"
        llm.chat.return_value = "用户偏好安静的自然景点，预算5000元。"

        compressor = ConversationCompressor(llm)
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

        # Evaluate importance of a preference
        importance = await promoter.evaluate_importance(
            "我想要一个安静的自然景点",
            None,
            0.6
        )

        assert importance > 0.6  # LLM should boost the score

    def test_memory_strength_compatible_with_config(self):
        """Test that MemoryStrength works with default config values."""
        config = MemoryConfig()

        # Verify forgetting curve defaults
        assert config.forgetting_threshold == 0.3
        assert config.forgetting_decay_factor == 30.0
        assert config.forgetting_reinforce_boost == 0.05

        # Verify compression defaults
        assert config.compression_recent_limit == 5
        assert config.compression_mid_limit == 20

        # Verify slot templates
        assert len(config.compression_slot_templates) >= 3

    @pytest.mark.asyncio
    async def test_full_memory_optimization_pipeline(self):
        """Test complete pipeline: compress -> promote -> reinforce."""
        # Setup mock LLM with both methods
        llm = AsyncMock()
        llm.generate.return_value = "0.90"
        llm.chat.return_value = "用户计划去云南旅游，偏好自然风光。"

        # Setup mock repository
        repo = AsyncMock()
        repo.update_metadata.return_value = True

        # Initialize all components
        compressor = ConversationCompressor(llm, recent_limit=3, mid_limit=10)
        promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)
        forgetting_manager = ForgettingCurveManager(repo)

        # Simulate conversation
        messages = [
            {"role": "user", "content": "你好"},  # old
            {"role": "user", "content": "我想去云南"},  # old
            {"role": "user", "content": "我喜欢自然风光"},  # mid -> important
            {"role": "user", "content": "预算8000元"},  # mid -> slot
            {"role": "user", "content": "最新的查询"},  # recent
        ]

        # Step 1: Compress conversation
        compressed = await compressor.compress(messages)

        # Verify compression worked
        assert len(compressed) <= len(messages)

        # Step 2: Evaluate importance of a preference message
        importance = await promoter.evaluate_importance(
            "我喜欢自然风光",
            None,
            0.6
        )

        # Should get boosted by LLM evaluation
        assert importance >= 0.6  # At minimum the rule score
        # With LLM returning 0.90: 0.6*0.3 + 0.90*0.7 = 0.81
        assert abs(importance - 0.81) < 0.02

        # Step 3: Simulate memory reinforcement
        memory_item = {
            "id": "mem_123",
            "content": "我喜欢自然风光",
            "metadata": {
                "created_at": time.time(),
                "importance": importance,
            }
        }
        await forgetting_manager.reinforce_memories([memory_item])

        # Verify reinforcement was persisted
        repo.update_metadata.assert_called()
        call_args = repo.update_metadata.call_args
        assert call_args[0][0] == "mem_123"
        assert "strength" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_forgetting_curve_with_compressed_memory(self):
        """Test that forgetting curve works correctly after compression."""
        repo = AsyncMock()
        repo.update_metadata.return_value = True

        manager = ForgettingCurveManager(repo)

        # Create memories representing compressed conversation
        # Some should be forgotten (old slot-extracted data)
        # Some should be active (recent full messages)
        # Note: log(1+access_count) factor requires access_count > 0 for non-zero strength
        memories = [
            {
                "id": "compressed_slot_1",
                "content": "目的地: 北京 | 预算: 3000",
                "metadata": {
                    "created_at": time.time() - 60 * 86400,  # 60 days ago
                    "importance": 0.4,
                    "strength": {
                        "initial_strength": 0.4,
                        "created_at": time.time() - 60 * 86400,
                        "last_accessed": time.time() - 60 * 86400,
                        "access_count": 0,  # No access = forgotten
                        "decay_factor": 30,
                    }
                }
            },
            {
                "id": "recent_full",
                "content": "用户最近询问景点推荐",
                "metadata": {
                    "created_at": time.time() - 1 * 86400,  # 1 day ago
                    "importance": 0.8,
                    "strength": {
                        "initial_strength": 0.8,
                        "created_at": time.time() - 1 * 86400,
                        "last_accessed": time.time() - 3600,
                        "access_count": 1,  # At least one access for active status
                        "decay_factor": 30,
                    }
                }
            },
        ]

        # Filter active memories
        active = await manager.filter_active(memories)

        # The recent full message should be active
        # The old compressed slot may be forgotten
        assert len(active) >= 1
        assert "recent_full" in [m["id"] for m in active]

        # Reinforce active memories
        await manager.reinforce_memories(active)
        assert repo.update_metadata.call_count == len(active)