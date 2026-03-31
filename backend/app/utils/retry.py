"""Retry decorator with fallback for tool reliability.

References:
- AI-04: Tool calling error handling and retry
- D-16: Retry up to 3 times on failure
- D-17: Return fallback values on failure
- D-18: Log tool failures for optimization
- 03-RESEARCH.md: Tool retry middleware pattern
"""

import asyncio
import functools
import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential: bool = True
):
    """Decorator for retrying failed async functions with exponential backoff.

    Per D-16: Retry up to 3 times on failure.
    Per 03-RESEARCH.md: Exponential backoff between retries.

    Args:
        max_attempts: Maximum number of retry attempts (default 3 per D-16)
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential: If True, use exponential backoff (2^n * base_delay)

    Example:
        @with_retry(max_attempts=3)
        async def fetch_weather(city: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_error = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    is_last_attempt = attempt == max_attempts - 1

                    if is_last_attempt:
                        logger.error(
                            f"[Retry] {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                    else:
                        # Calculate delay with exponential backoff
                        if exponential:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                        else:
                            delay = base_delay

                        logger.warning(
                            f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)

            # All attempts failed
            raise last_error

        return wrapper
    return decorator


def with_fallback(
    fallback_value: Any,
    max_attempts: int = 3,
    log_failures: bool = True
):
    """Decorator that returns fallback value instead of raising on failure.

    Per D-17: Return fallback values instead of error interruption.
    Per D-18: Log tool failures for optimization.

    Args:
        fallback_value: Value to return if all attempts fail
        max_attempts: Maximum retry attempts before using fallback
        log_failures: If True, log failures for monitoring

    Example:
        @with_fallback(fallback_value={"error": "Service unavailable"})
        async def fetch_weather(city: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if log_failures:
                        logger.warning(
                            f"[Fallback] {func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                        )

            # Log final failure per D-18
            if log_failures:
                logger.error(f"[Fallback] {func.__name__} using fallback after {max_attempts} failures")

            # Return fallback value instead of raising (per D-17)
            if callable(fallback_value):
                return fallback_value(last_error)
            return fallback_value

        return wrapper
    return decorator


def with_retry_and_fallback(
    fallback_value: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exponential: bool = True
):
    """Combined retry and fallback decorator.

    Retries on failure, returns fallback if all retries fail.

    Args:
        fallback_value: Value to return if all attempts fail
        max_attempts: Maximum retry attempts
        base_delay: Initial delay for exponential backoff
        exponential: Use exponential backoff

    Example:
        @with_retry_and_fallback(fallback_value={"weather": "暂时无法获取"})
        async def fetch_weather(city: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    is_last_attempt = attempt == max_attempts - 1

                    if not is_last_attempt:
                        if exponential:
                            delay = min(base_delay * (2 ** attempt), 10.0)
                        else:
                            delay = base_delay

                        logger.warning(
                            f"[RetryFallback] {func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                        )
                        await asyncio.sleep(delay)

            # All retries failed, return fallback
            logger.error(f"[RetryFallback] {func.__name__} returning fallback after {max_attempts} failures")

            if callable(fallback_value):
                return fallback_value(last_error)
            return fallback_value

        return wrapper
    return decorator
