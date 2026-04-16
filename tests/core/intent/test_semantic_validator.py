"""Tests for SemanticValidator functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.context import RequestContext, IntentResult
from app.core.intent.strategies.semantic_validator import SemanticValidator


class TestSemanticValidatorBasic:
    """Test basic SemanticValidator functionality."""

    def test_validator_initialization(self):
        """Test validator initializes correctly."""
        validator = SemanticValidator()
        assert validator.priority == 15
        assert validator.estimated_cost() == 150.0
        assert validator._min_confidence == 0.7

    def test_validator_with_custom_settings(self):
        """Test validator with custom settings."""
        validator = SemanticValidator(
            min_confidence=0.8,
            timeout=10,
        )
        assert validator._min_confidence == 0.8
        assert validator._timeout == 10


class TestSemanticValidatorShouldValidate:
    """Test should_validate logic."""

    def test_should_not_validate_non_rule_method(self):
        """Test that non-rule results are not validated."""
        validator = SemanticValidator()

        result = IntentResult(
            intent="query",
            confidence=0.9,
            method="llm",
        )

        assert not validator.should_validate(result)

    def test_should_not_validate_low_confidence(self):
        """Test that low confidence results are not validated."""
        validator = SemanticValidator()

        result = IntentResult(
            intent="query",
            confidence=0.5,
            method="rule",
        )

        assert not validator.should_validate(result)

    def test_should_validate_with_exclusion_keywords(self):
        """Test that results with exclusion keywords are validated."""
        validator = SemanticValidator()

        result = IntentResult(
            intent="query",
            confidence=0.8,
            method="rule",
            metadata={"exclusion_keywords": ["真好"]}
        )

        assert validator.should_validate(result)

    def test_should_not_validate_without_exclusion(self):
        """Test that results without exclusion keywords are not validated."""
        validator = SemanticValidator()

        result = IntentResult(
            intent="query",
            confidence=0.8,
            method="rule",
        )

        assert not validator.should_validate(result)


class TestSemanticValidatorValidate:
    """Test validation logic."""

    @pytest.mark.asyncio
    async def test_validation_passed(self):
        """Test when validation passes (intent is correct)."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value='{"valid": true}')

        validator = SemanticValidator(llm_client=mock_llm)

        context = RequestContext(message="北京天气怎么样")
        result = IntentResult(
            intent="query",
            confidence=0.85,
            method="rule",
            metadata={"exclusion_keywords": ["天气"]}
        )

        validated = await validator.validate(context, result)

        # Should return original result when validation passes
        assert validated.intent == "query"
        assert validated.method == "rule"

    @pytest.mark.asyncio
    async def test_validation_corrected(self):
        """Test when validation corrects intent."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value='{"valid": false, "correct_intent": "itinerary", "reasoning": "天气出现在旅游语境中"}')

        validator = SemanticValidator(llm_client=mock_llm)

        context = RequestContext(message="天气真好想去北京玩")
        result = IntentResult(
            intent="query",
            confidence=0.85,
            method="rule",
            metadata={"exclusion_keywords": ["真好"]}
        )

        validated = await validator.validate(context, result)

        # Should return corrected result
        assert validated.intent == "itinerary"
        assert validated.method == "semantic_correction"
        assert validated.confidence == 0.65

    @pytest.mark.asyncio
    async def test_validation_no_llm_client(self):
        """Test when no LLM client available."""
        validator = SemanticValidator(llm_client=None)

        context = RequestContext(message="天气真好想去北京玩")
        result = IntentResult(
            intent="query",
            confidence=0.85,
            method="rule",
            metadata={"exclusion_keywords": ["真好"]}
        )

        validated = await validator.validate(context, result)

        # Should return original result when no LLM client
        assert validated.intent == "query"
        assert validated.method == "rule"

    @pytest.mark.asyncio
    async def test_validation_on_llm_error(self):
        """Test graceful handling of LLM errors."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM error"))

        validator = SemanticValidator(llm_client=mock_llm)

        context = RequestContext(message="天气真好想去北京玩")
        result = IntentResult(
            intent="query",
            confidence=0.85,
            method="rule",
            metadata={"exclusion_keywords": ["真好"]}
        )

        validated = await validator.validate(context, result)

        # Should return original result on error (fail-safe)
        assert validated.intent == "query"
        assert validated.method == "rule"


class TestSemanticValidatorParseResponse:
    """Test response parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        validator = SemanticValidator()

        response = '{"valid": false, "correct_intent": "itinerary"}'
        parsed = validator._parse_response(response)

        assert parsed is not None
        assert parsed["valid"] is False
        assert parsed["correct_intent"] == "itinerary"

    def test_parse_json_in_markdown(self):
        """Test parsing JSON in markdown code block."""
        validator = SemanticValidator()

        response = '```json\n{"valid": true}\n```'
        parsed = validator._parse_response(response)

        assert parsed is not None
        assert parsed["valid"] is True

    def test_parse_invalid_response(self):
        """Test parsing invalid response returns None."""
        validator = SemanticValidator()

        response = "This is not JSON at all"
        parsed = validator._parse_response(response)

        assert parsed is None

    def test_parse_empty_response(self):
        """Test parsing empty response returns None."""
        validator = SemanticValidator()

        parsed = validator._parse_response("")
        assert parsed is None


class TestSemanticValidatorBadCases:
    """Test handling of specific Bad Cases."""

    @pytest.mark.asyncio
    async def test_weather_in_travel_context(self):
        """Test '天气真好想去北京玩' should be corrected to itinerary."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value='{"valid": false, "correct_intent": "itinerary", "reasoning": "用户真正意图是规划行程，天气只是背景描述"}')

        validator = SemanticValidator(llm_client=mock_llm)

        context = RequestContext(message="天气真好想去北京玩")
        result = IntentResult(
            intent="query",  # Initially classified as query due to "���气"
            confidence=0.85,
            method="rule",
            metadata={"exclusion_keywords": ["真好"]}
        )

        validated = await validator.validate(context, result)

        assert validated.intent == "itinerary"
        assert validated.method == "semantic_correction"

    @pytest.mark.asyncio
    async def test_chat_about_hotel(self):
        """Test '聊聊酒店' should be corrected to chat."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value='{"valid": false, "correct_intent": "chat", "reasoning": "用户想闲聊酒店话题，不是预订"}')

        validator = SemanticValidator(llm_client=mock_llm)

        context = RequestContext(message="聊聊酒店")
        result = IntentResult(
            intent="hotel",  # Initially classified as hotel due to "酒店"
            confidence=0.8,
            method="rule",
            metadata={"exclusion_keywords": ["聊聊"]}
        )

        validated = await validator.validate(context, result)

        assert validated.intent == "chat"
        assert validated.method == "semantic_correction"