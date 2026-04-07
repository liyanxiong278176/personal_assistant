"""Tests for TokenCompressor - budget-aware prompt compression

Tests the TokenCompressor's ability to:
1. Pass small prompts through unchanged
2. Trim large prompts that exceed token budget
3. Return appropriate warnings when compression occurs
4. Handle edge cases (empty input, exact budget boundary)
"""

import pytest

from app.core.context import RequestContext
from app.core.prompts.pipeline.compressor import TokenCompressor


class TestTokenCompressorBasic:
    """Basic token compressor functionality"""

    @pytest.mark.asyncio
    async def test_compressor_skips_small_prompt(self):
        """Test that prompts under the budget pass through unchanged"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        # Default max_tokens=16000, target_ratio=0.8 -> budget = 16000 * 0.8 * 4 = 51200 chars
        # Small prompt well under budget
        small_prompt = "帮我规划北京三日游"
        context = RequestContext(message=small_prompt)

        result = await compressor.process(small_prompt, context)

        assert result.success is True
        assert result.content == small_prompt
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_compressor_trims_large_prompt(self):
        """Test that prompts over the budget are trimmed with a warning"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        # Default max_tokens=16000, target_ratio=0.8 -> budget = 51200 chars
        # Create a prompt that exceeds the budget
        large_prompt = "A" * 60000  # 60000 chars > 51200 budget
        context = RequestContext(message=large_prompt)

        result = await compressor.process(large_prompt, context)

        assert result.success is True
        assert len(result.content) == 51200  # Trimmed to budget
        assert result.warning is not None
        assert "trimmed" in result.warning.lower()

    @pytest.mark.asyncio
    async def test_compressor_exact_budget_boundary(self):
        """Test behavior when prompt length is exactly at the budget"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        # Default max_tokens=16000, target_ratio=0.8 -> budget = 51200 chars
        exact_prompt = "B" * 51200
        context = RequestContext(message=exact_prompt)

        result = await compressor.process(exact_prompt, context)

        assert result.success is True
        assert result.content == exact_prompt
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_compressor_one_char_over_budget(self):
        """Test trimming when prompt is just one character over budget"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        budget = int(16000 * 0.8) * 4  # 51200 chars
        # One character over budget
        over_prompt = "C" * (budget + 1)
        context = RequestContext(message=over_prompt)

        result = await compressor.process(over_prompt, context)

        assert result.success is True
        assert len(result.content) == budget
        assert result.warning is not None


class TestTokenCompressorConfiguration:
    """Test TokenCompressor with different configurations"""

    @pytest.mark.asyncio
    async def test_custom_target_ratio(self):
        """Test with custom target_ratio of 0.5 (50% of max_tokens)"""
        compressor = TokenCompressor(target_ratio=0.5, chars_per_token=4)
        # max_tokens=16000, target_ratio=0.5 -> budget = 16000 * 0.5 * 4 = 32000 chars
        prompt = "D" * 40000  # Over 32000 budget
        context = RequestContext(message=prompt)

        result = await compressor.process(prompt, context)

        assert result.success is True
        assert len(result.content) == 32000  # Trimmed to 0.5 budget
        assert result.warning is not None

    @pytest.mark.asyncio
    async def test_custom_chars_per_token(self):
        """Test with custom chars_per_token (3 chars/token means more tokens)"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=3)
        # max_tokens=16000, target_ratio=0.8 -> budget = 16000 * 0.8 * 3 = 38400 chars
        prompt = "E" * 40000  # Over 38400 budget
        context = RequestContext(message=prompt)

        result = await compressor.process(prompt, context)

        assert result.success is True
        assert len(result.content) == 38400  # Trimmed to 3-char budget

    @pytest.mark.asyncio
    async def test_custom_max_tokens_in_context(self):
        """Test with custom max_tokens in RequestContext"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        # max_tokens=8000, target_ratio=0.8 -> budget = 8000 * 0.8 * 4 = 25600 chars
        prompt = "F" * 30000  # Over 25600 budget
        context = RequestContext(message=prompt, max_tokens=8000)

        result = await compressor.process(prompt, context)

        assert result.success is True
        assert len(result.content) == 25600


class TestTokenCompressorEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_empty_prompt(self):
        """Test handling of empty prompt"""
        compressor = TokenCompressor()
        context = RequestContext(message="")

        result = await compressor.process("", context)

        assert result.success is True
        assert result.content == ""
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_unicode_content(self):
        """Test that unicode characters are handled correctly"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        # Chinese chars count as single chars in len()
        unicode_prompt = "你好世界" * 10000  # 40000 chars
        context = RequestContext(message=unicode_prompt)

        result = await compressor.process(unicode_prompt, context)

        assert result.success is True
        # Budget is 51200, so no trimming needed
        assert result.content == unicode_prompt

    @pytest.mark.asyncio
    async def test_trimming_preserves_beginning(self):
        """Test that trimming removes content from the END, not the beginning"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        prompt = "BEGINNING" + "X" * 60000  # Over budget
        context = RequestContext(message=prompt)

        result = await compressor.process(prompt, context)

        assert result.success is True
        # Should start with "BEGINNING" - beginning is preserved
        assert result.content.startswith("BEGINNING")
        # Content length should equal budget (trimmed from end)
        budget = int(16000 * 0.8) * 4  # 51200
        assert len(result.content) == budget

    @pytest.mark.asyncio
    async def test_invalid_target_ratio_raises(self):
        """Test that invalid target_ratio raises ValueError"""
        with pytest.raises(ValueError, match="target_ratio"):
            TokenCompressor(target_ratio=0.0)

        with pytest.raises(ValueError, match="target_ratio"):
            TokenCompressor(target_ratio=1.5)

    @pytest.mark.asyncio
    async def test_invalid_chars_per_token_raises(self):
        """Test that non-positive chars_per_token raises ValueError"""
        with pytest.raises(ValueError, match="chars_per_token"):
            TokenCompressor(chars_per_token=0)

        with pytest.raises(ValueError, match="chars_per_token"):
            TokenCompressor(chars_per_token=-1)

    @pytest.mark.asyncio
    async def test_token_estimate_calculation(self):
        """Test the _estimate_tokens method directly"""
        compressor = TokenCompressor(chars_per_token=4)

        # 20 chars / 4 = 5 tokens
        assert compressor._estimate_tokens("A" * 20) == 5

        # 21 chars / 4 = 5 tokens (floor division)
        assert compressor._estimate_tokens("A" * 21) == 5

        # 24 chars / 4 = 6 tokens
        assert compressor._estimate_tokens("A" * 24) == 6

        # Empty string = 0 tokens
        assert compressor._estimate_tokens("") == 0

    @pytest.mark.asyncio
    async def test_warning_contains_token_info(self):
        """Test that warning message includes token count information"""
        compressor = TokenCompressor(target_ratio=0.8, chars_per_token=4)
        # 60000 chars / 4 = 15000 tokens
        # Budget = 51200 chars / 4 = 12800 tokens
        prompt = "G" * 60000
        context = RequestContext(message=prompt)

        result = await compressor.process(prompt, context)

        assert result.warning is not None
        assert "15000" in result.warning  # Original token count
        assert "12800" in result.warning  # Trimmed token count
