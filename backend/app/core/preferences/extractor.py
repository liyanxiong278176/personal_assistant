"""Preference Extractor - Coordinate preference matching and storage.

This module provides the PreferenceExtractor class which coordinates
between PreferenceMatcher for extraction and PreferenceRepository for
persistent storage. It filters results by confidence threshold and
automatically stores high-confidence preferences.
"""

import logging
from typing import List, Optional

from app.core.preferences.patterns import MatchedPreference, PreferenceMatcher
from app.core.preferences.repository import PreferenceRepository

logger = logging.getLogger(__name__)


class PreferenceExtractor:
    """Coordinate preference matching and storage.

    This class combines PreferenceMatcher and PreferenceRepository to
    provide a unified interface for extracting and storing user travel
    preferences. It filters results by confidence threshold and
    automatically stores high-confidence preferences.

    Attributes:
        matcher: PreferenceMatcher instance for extracting preferences
        repository: PreferenceRepository instance for persistent storage
        confidence_threshold: Minimum confidence for auto-storage (0.0-1.0)
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        repository: Optional[PreferenceRepository] = None,
    ):
        """Initialize the preference extractor.

        Args:
            confidence_threshold: Minimum confidence for auto-storage (0.0-1.0)
            repository: Optional PreferenceRepository instance.
                       If None, creates a new in-memory repository.
        """
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")

        self.matcher = PreferenceMatcher(confidence_threshold)
        self.repository = repository or PreferenceRepository()
        self.confidence_threshold = confidence_threshold
        logger.debug(
            f"[PreferenceExtractor] 初始化完成 | "
            f"threshold={confidence_threshold}"
        )

    async def extract(
        self,
        user_input: str,
        conversation_id: str,
        user_id: str,
    ) -> List[MatchedPreference]:
        """Extract preferences from user input and store high-confidence matches.

        This method extracts all preferences from the input text using
        the matcher, filters them by confidence threshold, and stores
        the high-confidence preferences in the repository.

        Args:
            user_input: The user's input text to analyze
            conversation_id: The conversation/session identifier
            user_id: The user identifier for storage

        Returns:
            List of MatchedPreference objects above confidence threshold
        """
        # Extract all matches from the input
        matches = self.matcher.extract(user_input)

        # Filter by confidence threshold
        filtered = [m for m in matches if m.confidence >= self.confidence_threshold]

        # Store high-confidence preferences
        if filtered:
            for pref in filtered:
                await self.add_preference(user_id, pref)

        logger.info(
            f"[PreferenceExtractor] 提取完成 | "
            f"user={user_id} | "
            f"conversation={conversation_id} | "
            f"input_len={len(user_input)} | "
            f"total={len(matches)} | "
            f"filtered={len(filtered)} | "
            f"stored={len(filtered)}"
        )

        return filtered

    async def add_preference(
        self,
        user_id: str,
        preference: MatchedPreference,
    ) -> None:
        """Add a single preference to the repository.

        This method upserts a preference into the repository using
        the high-confidence override strategy defined in PreferenceRepository.

        Args:
            user_id: The user identifier
            preference: The MatchedPreference to store
        """
        await self.repository.upsert(user_id, preference)
        logger.debug(
            f"[PreferenceExtractor] 偏好已存储 | "
            f"user={user_id} | "
            f"key={preference.key} | "
            f"value={preference.value} | "
            f"conf={preference.confidence}"
        )

    async def get_preferences(
        self,
        user_id: str,
        keys: Optional[List[str]] = None,
    ) -> dict:
        """Get stored preferences for a user.

        Retrieves preferences from the repository, optionally filtered
        by specific keys.

        Args:
            user_id: The user identifier
            keys: Optional list of preference keys to filter.
                  If None, returns all preferences.

        Returns:
            Dict mapping preference keys to MatchedPreference objects
        """
        result = await self.repository.get_user_preferences(user_id, keys)

        # Convert to simple dict for easier consumption
        output = {k: v.value for k, v in result.items()}

        logger.debug(
            f"[PreferenceExtractor] 偏好查询 | "
            f"user={user_id} | "
            f"keys={keys} | "
            f"found={len(output)}"
        )

        return output

    async def get_matched_preferences(
        self,
        user_id: str,
        keys: Optional[List[str]] = None,
    ) -> dict:
        """Get stored MatchedPreference objects for a user.

        Similar to get_preferences but returns the full MatchedPreference
        objects including confidence scores and metadata.

        Args:
            user_id: The user identifier
            keys: Optional list of preference keys to filter.
                  If None, returns all preferences.

        Returns:
            Dict mapping preference keys to MatchedPreference objects
        """
        result = await self.repository.get_user_preferences(user_id, keys)

        logger.debug(
            f"[PreferenceExtractor] 偏好查询(完整) | "
            f"user={user_id} | "
            f"keys={keys} | "
            f"found={len(result)}"
        )

        return result
