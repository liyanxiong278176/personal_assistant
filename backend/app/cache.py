"""Question caching service for cost control.

References:
- D-19: Implement question caching for exact match
- PITFALL.md: Unlimited API cost warning
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict

import httpx


class QuestionCache:
    """In-memory cache for exact question matches.

    Caches complete LLM responses for exact question+context matches
    to avoid redundant API calls.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize cache with TTL.

        Args:
            ttl_seconds: Time to live for cache entries (default 1 hour)
        """
        self._cache: Dict[str, dict] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0

    def _generate_key(self, question: str, context: list) -> str:
        """Generate cache key from question and context.

        Args:
            question: User's question
            context: Conversation context (list of messages)

        Returns:
            SHA256 hash of the normalized question+context
        """
        # Normalize context for caching
        context_str = json.dumps(context, sort_keys=True, ensure_ascii=False)
        combined = f"{question}:{context_str}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, question: str, context: list) -> Optional[str]:
        """Get cached response if available and not expired.

        Args:
            question: User's question
            context: Conversation context

        Returns:
            Cached response if found, None otherwise
        """
        key = self._generate_key(question, context)

        if key in self._cache:
            entry = self._cache[key]

            # Check if expired
            if datetime.utcnow() - entry["timestamp"] < self._ttl:
                self._hits += 1
                return entry["response"]
            else:
                # Remove expired entry
                del self._cache[key]

        self._misses += 1
        return None

    def set(self, question: str, context: list, response: str) -> None:
        """Cache a response.

        Args:
            question: User's question
            context: Conversation context
            response: LLM response to cache
        """
        key = self._generate_key(question, context)
        self._cache[key] = {
            "response": response,
            "timestamp": datetime.utcnow()
        }

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with hit rate and entry count
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "entries": len(self._cache)
        }


# Global cache instance
cache = QuestionCache(ttl_seconds=3600)
