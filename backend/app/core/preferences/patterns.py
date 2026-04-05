"""Preference Pattern Matcher - Extract travel preferences from Chinese text.

This module provides regex-based pattern matching for extracting travel
preferences from user messages. It supports destinations, budget, and duration.

Limitations:
- Chinese number normalization only supports single digits (一-九, 十).
- Compound numbers like "三千五百" or "三十天" are not properly normalized.
  For full compound number support, implement a proper Chinese numeral parser.
"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


class PreferenceType:
    """Preference type constants for categorizing extracted preferences.

    Note: Only DESTINATION, BUDGET, and DURATION have patterns defined.
    Other types can be added as needed with their own regex patterns.
    """

    DESTINATION = "destination"
    BUDGET = "budget"
    DURATION = "duration"


@dataclass
class MatchedPreference:
    """A preference extracted from user text.

    Attributes:
        key: The type of preference (e.g., 'destination', 'budget')
        value: The normalized extracted value
        confidence: Confidence score from 0.0 to 1.0
        source: Source of extraction (default: 'rule')
        raw_text: Original matched text from the input
        extracted_at: Timestamp of extraction (UTC)
    """

    key: str
    value: str
    confidence: float
    source: str = "rule"
    raw_text: Optional[str] = None
    extracted_at: datetime = None

    def __post_init__(self):
        """Set default timestamp after initialization."""
        if self.extracted_at is None:
            self.extracted_at = datetime.now(timezone.utc)


class PreferenceMatcher:
    """Regex-based preference extractor for Chinese travel text.

    This class uses compiled regex patterns to extract travel preferences
    from Chinese text. It includes confidence scoring and normalization
    for different preference types.
    """

    # Regex patterns for each preference type
    # Note: Chinese number patterns only support single digits (一-九, 十)
    # For compound numbers like "三千五百", users should use Arabic numerals
    PATTERNS = {
        PreferenceType.DESTINATION: [
            r"我想去\s*([^，。！？\s\n和]+?)(?:[，。！？\s\n和]|旅游|玩|逛|$)",
            r"去\s*([^，。！？\s\n和]+?)(?:[，。！？\s\n和]|旅游|玩|逛|$)",
            r"和\s*([^，。！？\s\n]+?)(?:[，。！？\s\n和]|旅游|玩|逛|$)",
            r"[,，]\s*([^，。！？\s\n]+?)\s*(?:旅游|玩|逛|去|，。！？|$)",
        ],
        PreferenceType.BUDGET: [
            r"预算\s*([一二三四五六七八九十\d]+)(?:元|块)?",
            r"([一二三四五六七八九十\d]+)(?:元|块)?\s*以内",
            r"([一二三四五六七八九十\d]+)(?:元|块)\s*左右",
            r"([一二三四五六七八九十\d]+)(?:元|块)\s*预算",
        ],
        PreferenceType.DURATION: [
            r"(\d+)\s*天",
            r"(\d+)\s*晚",
            r"([一二三四五六七八九十])\s*天",
            r"([一二三四五六七八九十])\s*晚",
        ],
    }

    # Chinese number to Arabic numeral mapping (single digits only)
    # Note: "十" is treated as 10, not as a position marker
    # This approach does NOT support compound numbers like "三十" or "三千五百"
    CHINESE_NUMBERS = {
        "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
        "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
        "两": "2",
    }

    def __init__(self, confidence_threshold: float = 0.7):
        """Initialize the preference matcher.

        Args:
            confidence_threshold: Minimum confidence for results (0.0-1.0)
        """
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.confidence_threshold = confidence_threshold
        self._compiled_patterns = self._compile_patterns()
        logger.debug(
            f"[PreferenceMatcher] 初始化完成 | "
            f"threshold={confidence_threshold}"
        )

    def _compile_patterns(self) -> dict:
        """Compile regex patterns for better performance.

        Returns:
            Dictionary mapping preference types to compiled regex lists
        """
        compiled = {}
        for key, patterns in self.PATTERNS.items():
            compiled[key] = [re.compile(p) for p in patterns]
        return compiled

    def extract(self, text: str) -> List[MatchedPreference]:
        """Extract all preferences from the given text.

        Args:
            text: Input text to analyze

        Returns:
            List of matched preferences above confidence threshold
        """
        results = []

        if not text or not text.strip():
            return results

        for pref_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    # Extract the captured value
                    value = match.group(1) if match.lastindex else match.group(0)
                    value = self._normalize_value(pref_type, value)

                    if not value:
                        continue

                    confidence = self._calculate_confidence(pref_type, match, text)

                    if confidence >= self.confidence_threshold:
                        results.append(MatchedPreference(
                            key=pref_type,
                            value=value,
                            confidence=confidence,
                            source="rule",
                            raw_text=match.group(0)
                        ))

        logger.debug(
            f"[PreferenceMatcher] 提取完成 | "
            f"input_len={len(text)} | "
            f"found={len(results)}"
        )
        return results

    def _normalize_value(self, pref_type: str, value: str) -> str:
        """Normalize extracted values based on preference type.

        Args:
            pref_type: Type of preference being normalized
            value: Raw extracted value

        Returns:
            Normalized value string
        """
        if not value:
            return ""

        if pref_type == PreferenceType.BUDGET:
            return self._normalize_budget(value)
        elif pref_type == PreferenceType.DURATION:
            return self._normalize_duration(value)
        elif pref_type == PreferenceType.DESTINATION:
            return self._normalize_destination(value)
        else:
            return value.strip()

    def _normalize_destination(self, value: str) -> str:
        """Normalize destination values by removing trailing keywords.

        Removes trailing travel-related keywords like '旅游', '玩', '逛'.

        Args:
            value: Raw destination string

        Returns:
            Normalized destination string
        """
        if not value:
            return ""

        # Strip trailing travel keywords
        normalized = value
        for keyword in ["旅游", "玩", "逛", "去"]:
            if normalized.endswith(keyword):
                normalized = normalized[:-len(keyword)].strip()
                break

        return normalized.strip()

    def _normalize_budget(self, value: str) -> str:
        """Normalize budget values to standard format.

        Converts Chinese numbers to Arabic numerals and ensures
        consistent unit formatting.

        Args:
            value: Raw budget string

        Returns:
            Normalized budget string (e.g., "5000元")
        """
        # Replace Chinese numbers
        normalized = value
        for cn, num in self.CHINESE_NUMBERS.items():
            normalized = normalized.replace(cn, num)

        # Extract all numeric parts
        nums = re.findall(r"\d+", normalized)
        if nums:
            return f"{nums[0]}元"
        return value.strip()

    def _normalize_duration(self, value: str) -> str:
        """Normalize duration values to standard format.

        Converts nights to days and Chinese numbers to Arabic numerals.

        Args:
            value: Raw duration string

        Returns:
            Normalized duration string (e.g., "5天")
        """
        # Replace Chinese numbers
        normalized = value
        for cn, num in self.CHINESE_NUMBERS.items():
            normalized = normalized.replace(cn, num)

        # Extract numeric part
        nums = re.findall(r"\d+", normalized)
        if nums:
            return f"{nums[0]}天"
        return value.strip()

    def _calculate_confidence(
        self, pref_type: str, match: re.Match, text: str
    ) -> float:
        """Calculate confidence score for a match.

        Confidence is based on:
        - Presence of strong indicator keywords
        - Numeric content in the match
        - Position in the text (earlier is better)

        Args:
            pref_type: Type of preference
            match: Regex match object
            text: Full input text

        Returns:
            Confidence score from 0.0 to 1.0
        """
        confidence = 0.5  # Base confidence
        matched_text = match.group(0)

        # Boost for strong indicator phrases
        if "我想去" in matched_text or "我想" in matched_text:
            confidence += 0.3

        if "预算" in matched_text:
            confidence += 0.3

        # Boost for numeric content
        if re.search(r"\d+", matched_text):
            confidence += 0.1

        # Small boost for early position (first 30% of text)
        pos = match.start()
        if pos < len(text) * 0.3:
            confidence += 0.1

        return min(confidence, 1.0)
