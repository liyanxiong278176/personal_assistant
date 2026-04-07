"""Circuit Breaker implementation for cache layer fault tolerance.

The Circuit Breaker pattern prevents cascading failures by:
1. Detecting when a dependent service is failing
2. Temporarily blocking requests to that service
3. Allowing a limited number of test requests to detect recovery

State transitions:
    CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing) -> CLOSED
         ^______________________________|
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states.

    CLOSED: Requests pass through normally. Failures are counted.
    OPEN: Requests are blocked immediately. Background timeout running.
    HALF_OPEN: Limited requests allowed to test if service recovered.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of consecutive failures before opening circuit
        timeout_seconds: How long to stay in OPEN state before attempting recovery
        success_threshold: Consecutive successes needed in HALF_OPEN to close circuit
        half_open_max_calls: Maximum requests allowed in HALF_OPEN state
    """

    failure_threshold: int = 5
    timeout_seconds: int = 60
    success_threshold: int = 1
    half_open_max_calls: int = 3


@dataclass
class CircuitBreakerStats:
    """Statistics about circuit breaker state."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    opened_at: Optional[float] = None
    total_failures: int = 0
    total_successes: int = 0
    half_open_calls: int = 0


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures.

    Example:
        >>> breaker = CircuitBreaker()
        >>> if breaker.can_execute():
        ...     try:
        ...         result = risky_operation()
        ...         breaker.record_success()
        ...     except Exception:
        ...         breaker.record_failure()
        ... else:
        ...     # Use fallback/degraded path
        ...     result = fallback_operation()
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker with configuration.

        Args:
            config: Circuit breaker configuration. Defaults to sensible defaults.
        """
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self _lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    def can_execute(self) -> bool:
        """Check if execution is allowed through the circuit.

        Returns:
            True if request should proceed, False if circuit is open.

        In OPEN state, checks if timeout has elapsed to transition to HALF_OPEN.
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if we should transition to HALF_OPEN
            if self._should_attempt_reset():
                self._transition_to_half_open()
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # Allow limited requests through to test recovery
            return self._stats.half_open_calls < self._config.half_open_max_calls

        return False

    def record_success(self):
        """Record a successful operation.

        May transition states:
        - HALF_OPEN -> CLOSED if success threshold reached
        - Always resets consecutive failure counter
        """
        self._stats.success_count += 1
        self._stats.consecutive_successes += 1
        self._stats.total_successes += 1
        self._stats.consecutive_failures = 0
        self._stats.last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            if self._stats.consecutive_successes >= self._config.success_threshold:
                self._transition_to_closed()
        elif self._state == CircuitState.CLOSED:
            logger.debug(
                f"[CircuitBreaker] Success recorded in CLOSED state. "
                f"Consecutive successes: {self._stats.consecutive_successes}"
            )

    def record_failure(self):
        """Record a failed operation.

        May transition states:
        - CLOSED -> OPEN if failure threshold reached
        - HALF_OPEN -> OPEN on any failure
        """
        self._stats.failure_count += 1
        self._stats.consecutive_failures += 1
        self._stats.total_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = time.time()

        if self._state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self._config.failure_threshold:
                self._transition_to_open()
        elif self._state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN immediately reopens
            self._transition_to_open()

    def get_stats(self) -> dict:
        """Get current circuit breaker statistics.

        Returns:
            Dictionary containing:
                - state: Current CircuitState
                - failure_count: Total failures in current state
                - success_count: Total successes in current state
                - consecutive_failures: Current consecutive failure streak
                - consecutive_successes: Current consecutive success streak
                - last_failure_time: Timestamp of last failure
                - last_success_time: Timestamp of last success
                - opened_at: Timestamp when circuit last opened
                - total_failures: All-time failures
                - total_successes: All-time successes
                - half_open_calls: Calls made in HALF_OPEN state
        """
        return {
            "state": self._state.value,
            "failure_count": self._stats.failure_count,
            "success_count": self._stats.success_count,
            "consecutive_failures": self._stats.consecutive_failures,
            "consecutive_successes": self._stats.consecutive_successes,
            "last_failure_time": self._stats.last_failure_time,
            "last_success_time": self._stats.last_success_time,
            "opened_at": self._stats.opened_at,
            "total_failures": self._stats.total_failures,
            "total_successes": self._stats.total_successes,
            "half_open_calls": self._stats.half_open_calls,
        }

    def reset(self):
        """Manually reset the circuit breaker to CLOSED state.

        Useful for testing or manual recovery intervention.
        """
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        logger.info("[CircuitBreaker] Manually reset to CLOSED state")

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._stats.opened_at is None:
            return True

        elapsed = time.time() - self._stats.opened_at
        return elapsed >= self._config.timeout_seconds

    def _transition_to_open(self):
        """Transition from CLOSED/HALF_OPEN to OPEN state."""
        self._state = CircuitState.OPEN
        self._stats.opened_at = time.time()
        self._stats.half_open_calls = 0
        logger.warning(
            f"[CircuitBreaker] Circuit OPENED after "
            f"{self._stats.consecutive_failures} consecutive failures. "
            f"Will attempt recovery in {self._config.timeout_seconds}s"
        )

    def _transition_to_half_open(self):
        """Transition from OPEN to HALF_OPEN state."""
        self._state = CircuitState.HALF_OPEN
        self._stats.half_open_calls = 0
        self._stats.consecutive_failures = 0
        self._stats.consecutive_successes = 0
        logger.info(
            f"[CircuitBreaker] Circuit HALF_OPEN. "
            f"Allowing {self._config.half_open_max_calls} test requests"
        )

    def _transition_to_closed(self):
        """Transition from HALF_OPEN to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._stats.failure_count = 0
        self._stats.success_count = 0
        self._stats.half_open_calls = 0
        logger.info(
            f"[CircuitBreaker] Circuit CLOSED after "
            f"{self._stats.consecutive_successes} consecutive successes. "
            f"Service recovered."
        )


class CircuitBreakerDecorator:
    """Decorator for automatically wrapping functions with circuit breaker.

    Example:
        >>> breaker = CircuitBreaker()
        >>> @CircuitBreakerDecorator(breaker, fallback_value="default")
        ... def risky_operation():
        ...     return external_api_call()
    """

    def __init__(
        self,
        breaker: CircuitBreaker,
        fallback_value: any = None,
        raise_on_open: bool = False,
    ):
        """Initialize decorator.

        Args:
            breaker: CircuitBreaker instance to use
            fallback_value: Value to return when circuit is open
            raise_on_open: If True, raises CircuitOpenError instead of returning fallback
        """
        self.breaker = breaker
        self.fallback_value = fallback_value
        self.raise_on_open = raise_on_open

    def __call__(self, func):
        """Wrap the function with circuit breaker logic."""

        def wrapper(*args, **kwargs):
            if not self.breaker.can_execute():
                if self.raise_on_open:
                    from backend.app.core.cache.errors import CircuitOpenError

                    raise CircuitOpenError(
                        f"Circuit breaker is OPEN for {func.__name__}"
                    )
                logger.debug(
                    f"[CircuitBreaker] Circuit OPEN, using fallback for {func.__name__}"
                )
                return self.fallback_value

            try:
                result = func(*args, **kwargs)
                self.breaker.record_success()
                return result
            except Exception as e:
                self.breaker.record_failure()
                logger.debug(
                    f"[CircuitBreaker] Exception in {func.__name__}: {e}"
                )
                raise

        return wrapper
