"""CacheStrategy - LRU cache for classification results.

Priority: 0 (highest - executes first)
Cost: 0.0 (in-memory lookup)
"""

import hashlib
import logging
from collections import OrderedDict
from typing import Optional

from app.core.context import RequestContext, IntentResult

logger = logging.getLogger(__name__)


class ClassificationCache:
    """LRU cache for intent classification results.

    Cache key format: "intent:{md5(message)}:image={has_image}"
    """

    def __init__(self, max_size: int = 1000):
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries to store
        """
        self._cache: OrderedDict[str, IntentResult] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, message: str, has_image: bool) -> Optional[IntentResult]:
        """Get cached result for a message.

        Args:
            message: User message
            has_image: Whether message contains an image

        Returns:
            Cached IntentResult or None if not found
        """
        key = self._make_key(message, has_image)

        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"[Cache] HIT for {key[:32]}...")
            return self._cache[key]

        self._misses += 1
        logger.debug(f"[Cache] MISS for {key[:32]}...")
        return None

    def put(self, message: str, has_image: bool, result: IntentResult) -> None:
        """Store a classification result in cache.

        Args:
            message: User message
            has_image: Whether message contains an image
            result: Classification result to cache
        """
        key = self._make_key(message, has_image)

        # Update existing or add new
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = result

        # Evict oldest if over capacity
        if len(self._cache) > self._max_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            logger.debug(f"[Cache] Evicted {oldest[:32]}...")

        logger.debug(f"[Cache] STORED {key[:32]}... (size: {len(self._cache)}/{self._max_size})")

    def _make_key(self, message: str, has_image: bool) -> str:
        """Create cache key from message and image flag.

        Args:
            message: User message
            has_image: Whether message contains an image

        Returns:
            Cache key string
        """
        # MD5 hash of message + image flag
        content = f"{message}:image={has_image}"
        hash_hex = hashlib.md5(content.encode()).hexdigest()
        return f"intent:{hash_hex}"

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.debug("[Cache] Cleared")

    def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, size
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "size": len(self._cache),
            "max_size": self._max_size,
        }


class CacheStrategy:
    """Cache-first strategy for intent classification.

    This strategy executes first (priority=0) to check for cached results.
    If cache hits, classification is complete immediately.
    If cache misses, strategy returns None to allow next strategy to run.

    Note: This strategy doesn't actually classify - it just looks up cached results.
    The router must handle storing results after successful classification.
    """

    def __init__(self, cache: Optional[ClassificationCache] = None):
        """Initialize cache strategy.

        Args:
            cache: Shared cache instance (creates new if None)
        """
        self._cache = cache or ClassificationCache()

    @property
    def priority(self) -> int:
        """Priority 0 - executes first."""
        return 0

    @property
    def cache(self) -> ClassificationCache:
        """Get the underlying cache instance.

        Returns:
            The ClassificationCache for storing results
        """
        return self._cache

    def estimated_cost(self) -> float:
        """Zero cost - in-memory lookup."""
        return 0.0

    async def can_handle(self, context: RequestContext) -> bool:
        """Always returns True - cache is checked for every request."""
        return True

    async def classify(self, context: RequestContext) -> Optional[IntentResult]:
        """Look up cached result for this request.

        Args:
            context: The request context

        Returns:
            Cached IntentResult or None if not cached
        """
        return self._cache.get(context.message, context.has_image)
