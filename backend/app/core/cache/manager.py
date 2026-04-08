"""CacheManager - unified cache entry point with circuit breaker.

Provides circuit breaker, automatic fallback, and metrics recording.
"""
import logging
import time
from typing import Optional, Dict

from app.core.cache.base import ICacheStore
from app.core.cache.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.core.cache.errors import CacheConnectionError, CircuitOpenError
from app.core.cache.ttl import CacheTTL
from app.core.metrics.collector import global_collector
from app.core.metrics.definitions import CacheMetric
from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Cache manager with circuit breaker and automatic fallback.

    Responsibilities:
    - Unified cache access entry point
    - Circuit breaker management
    - Automatic fallback to secondary store
    - Metrics recording
    """

    def __init__(
        self,
        primary_store: ICacheStore,
        fallback_store: ICacheStore,
        circuit_config: Optional[CircuitBreakerConfig] = None
    ):
        """Initialize cache manager.

        Args:
            primary_store: Primary cache store (Redis).
            fallback_store: Fallback store (PostgreSQL).
            circuit_config: Circuit breaker configuration.
        """
        self._primary = primary_store
        self._fallback = fallback_store
        self._circuit = CircuitBreaker(
            circuit_config or CircuitBreakerConfig(
                failure_threshold=settings.cache_circuit_threshold,
                timeout_seconds=settings.cache_circuit_timeout
            )
        )

        logger.info(
            f"[CacheManager] Initialized | "
            f"primary={type(primary_store).__name__} | "
            f"fallback={type(fallback_store).__name__}"
        )

    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """Get session data with circuit breaker and fallback.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            Session data dict if found, None otherwise.
        """
        start = time.perf_counter()
        fallback_used = False
        hit = False

        # Check circuit breaker
        if not self._circuit.can_execute():
            logger.warning("[CacheManager] Circuit OPEN, using fallback")
            fallback_used = True
            result = await self._fallback.get_session(conversation_id)
            await self._record_metric("get_session", hit, start, fallback_used)
            return result

        # Try primary store
        try:
            result = await self._primary.get_session(conversation_id)
            hit = result is not None

            if hit:
                self._circuit.record_success()
            else:
                # Cache miss is not a failure
                pass

            await self._record_metric("get_session", hit, start, False)
            return result

        except (CacheConnectionError, Exception) as e:
            logger.warning(f"[CacheManager] Primary failed: {e}, using fallback")
            self._circuit.record_failure()
            fallback_used = True

            result = await self._fallback.get_session(conversation_id)
            await self._record_metric("get_session", result is not None, start, True)
            return result

    async def set_session(self, conversation_id: str, data: Dict, ttl: Optional[int] = None) -> None:
        """Set session data.

        Args:
            conversation_id: Conversation identifier.
            data: Session data dictionary.
            ttl: Time-to-live in seconds.
        """
        if ttl is None:
            ttl = CacheTTL.SESSION

        start = time.perf_counter()

        # Skip write if circuit is open
        if not self._circuit.can_execute():
            logger.debug("[CacheManager] Circuit OPEN, skipping set")
            return

        try:
            await self._primary.set_session(conversation_id, data, ttl)
            self._circuit.record_success()
            await self._record_metric("set_session", True, start, False)

        except (CacheConnectionError, Exception) as e:
            logger.warning(f"[CacheManager] Set failed: {e}")
            self._circuit.record_failure()
            await self._record_metric("set_session", False, start, True)

    async def delete_session(self, conversation_id: str) -> bool:
        """Delete session data.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            if self._circuit.can_execute():
                return await self._primary.delete_session(conversation_id)
        except Exception as e:
            logger.warning(f"[CacheManager] Delete failed: {e}")

        return await self._fallback.delete_session(conversation_id)

    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """Get slot data.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            Slot data dict if found, None otherwise.
        """
        start = time.perf_counter()

        if not self._circuit.can_execute():
            return await self._fallback.get_slots(conversation_id)

        try:
            result = await self._primary.get_slots(conversation_id)
            if result:
                self._circuit.record_success()
            await self._record_metric("get_slots", result is not None, start, False)
            return result

        except Exception as e:
            self._circuit.record_failure()
            result = await self._fallback.get_slots(conversation_id)
            await self._record_metric("get_slots", result is not None, start, True)
            return result

    async def set_slots(self, conversation_id: str, slots: Dict, ttl: Optional[int] = None) -> None:
        """Set slot data.

        Args:
            conversation_id: Conversation identifier.
            slots: Slot data dictionary.
            ttl: Time-to-live in seconds.
        """
        if ttl is None:
            ttl = CacheTTL.SLOTS

        if not self._circuit.can_execute():
            return

        try:
            await self._primary.set_slots(conversation_id, slots, ttl)
            self._circuit.record_success()
        except Exception as e:
            logger.warning(f"[CacheManager] set_slots failed: {e}")
            self._circuit.record_failure()

    async def delete_slots(self, conversation_id: str) -> bool:
        """Delete slot data.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            if self._circuit.can_execute():
                return await self._primary.delete_slots(conversation_id)
        except Exception:
            pass

        return False

    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """Get user preferences.

        Args:
            user_id: User identifier.

        Returns:
            User preferences dict if found, None otherwise.
        """
        start = time.perf_counter()

        if not self._circuit.can_execute():
            return await self._fallback.get_user_prefs(user_id)

        try:
            result = await self._primary.get_user_prefs(user_id)
            if result:
                self._circuit.record_success()
            await self._record_metric("get_user_prefs", result is not None, start, False)
            return result

        except Exception as e:
            self._circuit.record_failure()
            result = await self._fallback.get_user_prefs(user_id)
            await self._record_metric("get_user_prefs", result is not None, start, True)
            return result

    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: Optional[int] = None) -> None:
        """Set user preferences.

        Args:
            user_id: User identifier.
            prefs: Preferences dictionary.
            ttl: Time-to-live in seconds.
        """
        if ttl is None:
            ttl = CacheTTL.USER_PREFS

        if not self._circuit.can_execute():
            return

        try:
            await self._primary.set_user_prefs(user_id, prefs, ttl)
            self._circuit.record_success()
        except Exception as e:
            logger.warning(f"[CacheManager] set_user_prefs failed: {e}")
            self._circuit.record_failure()

    async def delete_user_prefs(self, user_id: str) -> bool:
        """Delete user preferences.

        Args:
            user_id: User identifier.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            if self._circuit.can_execute():
                return await self._primary.delete_user_prefs(user_id)
        except Exception:
            pass

        return False

    async def health_check(self) -> Dict:
        """Health check for all stores.

        Returns:
            Dictionary with primary/fallback health and circuit state.
        """
        primary_healthy = False
        fallback_healthy = False

        try:
            primary_healthy = await self._primary.health_check()
        except Exception as e:
            logger.warning(f"[CacheManager] Primary health check failed: {e}")

        try:
            fallback_healthy = await self._fallback.health_check()
        except Exception as e:
            logger.warning(f"[CacheManager] Fallback health check failed: {e}")

        return {
            "primary": primary_healthy,
            "fallback": fallback_healthy,
            "circuit_state": self._circuit.state.value,
            "circuit_stats": self._circuit.get_stats()
        }

    async def _record_metric(self, operation: str, hit: bool, start: float, fallback_used: bool) -> None:
        """Record cache metric.

        Args:
            operation: Operation name.
            hit: Whether cache hit.
            start: Start time for latency calculation.
            fallback_used: Whether fallback was used.
        """
        latency_ms = (time.perf_counter() - start) * 1000
        metric = CacheMetric(
            operation=operation,
            hit=hit,
            latency_ms=latency_ms,
            fallback_used=fallback_used
        )
        await global_collector.record_cache(metric)

    def get_circuit_state(self) -> str:
        """Get circuit breaker state.

        Returns:
            Current circuit state as string.
        """
        return self._circuit.state.value

    def get_circuit_stats(self) -> dict:
        """Get circuit breaker statistics.

        Returns:
            Circuit breaker statistics dictionary.
        """
        return self._circuit.get_stats()
