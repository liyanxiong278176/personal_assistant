"""TTL (Time-To-Live) constants for cache entries."""

import random


class CacheTTL:
    """TTL constants in seconds for various cache entry types."""

    # Session-level cache: 1 hour
    SESSION = 3600

    # Slot/state cache: 30 minutes
    SLOTS = 1800

    # User preferences cache: 7 days
    USER_PREFS = 604800

    @staticmethod
    def with_jitter(base_ttl: int, jitter_percent: float = 0.1) -> int:
        """
        Apply random jitter to a TTL value to prevent cache stampedes.

        Args:
            base_ttl: Base TTL value in seconds.
            jitter_percent: Jitter as a fraction of base_ttl (default 10%).

        Returns:
            TTL value with jitter applied, bounded to a minimum of 1 second.
        """
        jitter_range = base_ttl * jitter_percent
        jitter = random.uniform(-jitter_range, jitter_range)
        return max(1, int(base_ttl + jitter))
