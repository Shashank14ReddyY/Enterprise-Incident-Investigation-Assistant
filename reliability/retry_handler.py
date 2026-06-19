"""
retry_handler.py
Exponential-backoff retry decorator for LLM API calls and any I/O operation
that can transiently fail (rate limits, network blips, timeouts).

Usage:
    from reliability.retry_handler import with_retry

    @with_retry()
    def call_llm():
        return ask(system, user)

    # or wrap an existing call inline:
    result = with_retry()(some_fn)(arg1, arg2)
"""

from __future__ import annotations
import logging
import time
from functools import wraps
from typing import Callable, Tuple, Type

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError,
)

logger = logging.getLogger(__name__)

# Exception types that should trigger a retry
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
    ConnectionError,
    TimeoutError,
    OSError,
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_WAIT_MIN = 2      # seconds — first retry waits ~2s
DEFAULT_WAIT_MAX = 30     # seconds — cap on exponential growth
DEFAULT_MULTIPLIER = 2    # doubles on each retry


def with_retry(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    wait_min: float = DEFAULT_WAIT_MIN,
    wait_max: float = DEFAULT_WAIT_MAX,
    multiplier: float = DEFAULT_MULTIPLIER,
    reraise: bool = True,
) -> Callable:
    """
    Returns a decorator that retries the wrapped function on transient failures.

    Args:
        max_attempts:  Total number of attempts (first try + retries).
        wait_min:      Minimum wait between retries in seconds.
        wait_max:      Maximum wait between retries in seconds.
        multiplier:    Exponential growth factor.
        reraise:       If True, re-raise the last exception after exhausting retries.
                       If False, return None on final failure.

    Example:
        @with_retry(max_attempts=4, wait_min=1, wait_max=20)
        def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @retry(
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=multiplier, min=wait_min, max=wait_max),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=reraise,
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def retry_call(
    func: Callable,
    *args,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    **kwargs,
):
    """
    Inline retry helper — retries func(*args, **kwargs) without decorating.

    Returns the function's return value, or None if all attempts fail.

    Example:
        result = retry_call(ask, system_prompt, user_prompt, max_attempts=3)
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            wait = min(DEFAULT_WAIT_MIN * (DEFAULT_MULTIPLIER ** (attempt - 1)), DEFAULT_WAIT_MAX)
            logger.warning(
                "Attempt %d/%d failed for %s: %s. Retrying in %.1fs…",
                attempt, max_attempts, func.__name__, exc, wait,
            )
            if attempt < max_attempts:
                time.sleep(wait)
        except Exception as exc:
            # Non-retryable — surface immediately
            logger.error("Non-retryable error in %s: %s", func.__name__, exc)
            raise

    logger.error("All %d attempts failed for %s. Last error: %s",
                 max_attempts, func.__name__, last_exc)
    return None
