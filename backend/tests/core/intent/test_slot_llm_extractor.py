"""Tests for LLMSlotExtractor - LLM Function Calling based slot extraction."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.intent.slot_llm_extractor import LLMSlotExtractor, SLOT_TOOL_DEFINITION
from app.core.intent.slot_extractor import SlotResult
from app.core.llm.client import ToolCall


@pytest.fixture
def mock_llm_client():
    """Mock LLM client with Function Calling."""
    client = MagicMock()
    client.chat_with_tools = AsyncMock()
    return client


@pytest.fixture
def llm_extractor(mock_llm_client):
    return LLMSlotExtractor(llm_client=mock_llm_client)


class TestSlotToolDefinition:
    """Test SLOT_TOOL_DEFINITION structure."""

    def test_slot_tool_definition_valid(self):
        """Test: Tool definition has required fields."""
        assert SLOT_TOOL_DEFINITION["name"] == "extract_travel_slots"
        assert "destination" in SLOT_TOOL_DEFINITION["parameters"]["properties"]
        assert "days" in SLOT_TOOL_DEFINITION["parameters"]["properties"]

    def test_slot_tool_definition_all_required_slots(self):
        """Test: Tool definition includes all travel slots."""
        props = SLOT_TOOL_DEFINITION["parameters"]["properties"]
        expected_slots = [
            "destination", "destinations", "start_date", "end_date",
            "days", "travelers", "budget_level", "budget_amount", "interests"
        ]
        for slot in expected_slots:
            assert slot in props, f"Missing slot: {slot}"


class TestLLMSlotExtractor:
    """Test LLM Function Calling slot extraction."""

    @pytest.mark.asyncio
    async def test_extract_with_tool_call(self, llm_extractor, mock_llm_client):
        """Test: Parse tool call result into SlotResult."""
        mock_llm_client.chat_with_tools.return_value = (
            "",  # No content
            [ToolCall(
                id="call1",
                name="extract_travel_slots",
                arguments={"destination": "北京", "days": 3}
            )]
        )

        result = await llm_extractor.extract("想去北京玩三天")

        assert result.destination == "北京"
        assert result.days == 3

    @pytest.mark.asyncio
    async def test_extract_no_tool_call_returns_pre_extracted(self, llm_extractor, mock_llm_client):
        """Test: No tool call returns pre-extracted result."""
        mock_llm_client.chat_with_tools.return_value = ("好的", [])

        pre = SlotResult(destination="上海", days=5)
        result = await llm_extractor.extract("上海五日游", pre_extracted=pre)

        assert result.destination == "上海"  # Pre-extracted preserved

    @pytest.mark.asyncio
    async def test_merge_rule_first(self, llm_extractor, mock_llm_client):
        """Test: Merge strategy - rule result takes priority."""
        mock_llm_client.chat_with_tools.return_value = (
            "",
            [ToolCall(
                id="call1",
                name="extract_travel_slots",
                arguments={"destination": "成都", "days": 7}
            )]
        )

        # Rule already extracted destination
        pre = SlotResult(destination="北京", days=None)
        result = await llm_extractor.extract("北京七日游", pre_extracted=pre)

        # Rule destination preserved, LLM days filled
        assert result.destination == "北京"  # Rule priority
        assert result.days == 7  # LLM filled missing

    @pytest.mark.asyncio
    async def test_extract_multiple_destinations(self, llm_extractor, mock_llm_client):
        """Test: Extract multiple destinations."""
        mock_llm_client.chat_with_tools.return_value = (
            "",
            [ToolCall(
                id="call1",
                name="extract_travel_slots",
                arguments={"destinations": ["北京", "上海", "杭州"], "days": 7}
            )]
        )

        result = await llm_extractor.extract("想去北京上海杭州玩七天")

        assert result.destinations == ["北京", "上海", "杭州"]
        assert result.days == 7

    @pytest.mark.asyncio
    async def test_extract_with_budget_and_interests(self, llm_extractor, mock_llm_client):
        """Test: Extract budget level and interests."""
        mock_llm_client.chat_with_tools.return_value = (
            "",
            [ToolCall(
                id="call1",
                name="extract_travel_slots",
                arguments={
                    "destination": "三亚",
                    "days": 5,
                    "budget_level": "high",
                    "interests": ["beach", "food"]
                }
            )]
        )

        result = await llm_extractor.extract("想去三亚玩五天，预算高一点，喜欢海滩和美食")

        assert result.destination == "三亚"
        assert result.days == 5
        assert result.budget == "high"
        assert result.interests == ["beach", "food"]

    @pytest.mark.asyncio
    async def test_extract_error_returns_pre_extracted(self, llm_extractor, mock_llm_client):
        """Test: On error, return pre-extracted result."""
        mock_llm_client.chat_with_tools.side_effect = Exception("API error")

        pre = SlotResult(destination="西安", days=3)
        result = await llm_extractor.extract("西安三日游", pre_extracted=pre)

        # Should fall back to pre-extracted
        assert result.destination == "西安"
        assert result.days == 3

    @pytest.mark.asyncio
    async def test_extract_without_pre_extracted_returns_empty_on_error(self, llm_extractor, mock_llm_client):
        """Test: On error without pre-extracted, return empty SlotResult."""
        mock_llm_client.chat_with_tools.side_effect = Exception("API error")

        result = await llm_extractor.extract("随便聊聊")

        # Should return empty result
        assert result.destination is None
        assert result.days is None
