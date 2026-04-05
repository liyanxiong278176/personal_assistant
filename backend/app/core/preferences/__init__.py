"""Preferences module for extracting and managing user travel preferences.

This module provides pattern-based extraction of travel preferences from
Chinese text input, including destinations, budget, duration, and more.
"""

from app.core.preferences.patterns import (
    PreferenceType,
    MatchedPreference,
    PreferenceMatcher,
)

__all__ = [
    "PreferenceType",
    "MatchedPreference",
    "PreferenceMatcher",
]
