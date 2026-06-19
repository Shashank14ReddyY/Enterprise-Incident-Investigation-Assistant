"""
timeout_handler.py
Per-agent timeout enforcement using threading.
If an agent call takes longer than the allowed seconds, it is cancelled
and a TimeoutError is raised — which the retry_handler can catch and retry.

Usage:
    from reliability.timeout_handler import with_timeout, run_with_timeout

    @with_timeout(seconds=30)
    def slow_agent_call():
        return ask(system, user)

    # Or inline:
    result = run_with_timeout(ask, system, user, timeout=30)
"""

from __future__ import annotations
import logging
import threading
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Default per-agent timeout budgets (seconds)
AGENT_TIMEOUTS: dict[str, int] = {
    "Researcher Agent":    45,
    "Incident Agent":      60,
    "Root Cause Agent":    60,
    "Risk Agent":          45,
    "Reviewer Agent":      45,
    "Report Writer Agent": 90,
    "default":             60,
}


class TimeoutError(Exception):
    """Raised when a function exceeds its allowed execution time."""


def get_timeout(agent_name: str) -> int:
    """Look up the configured timeout for a named agent."""
    return AGENT_TIMEOUTS.get(agent_name, AGENT_TIMEOUTS["default"])


def run_with_timeout(
    func: Callable,
    *args,
    timeout: int = 60,
    **kwargs,
) -> Any:
    """
    Run func(*args, **kwargs) in a daemon thread.
    If it doesn't complete within `timeout` seconds, raise TimeoutError.

    Returns the function's return value on success.

    Note: Python threads cannot be hard-killed, so the underlying call
    continues running in the background after a timeout. For LLM calls
    this is acceptable — the thread will eventually finish and be GC'd.
    """
    result_holder: list[Any] = [None]
    exc_holder: list[Optional[Exception]] = [None]

    def target():
        try:
            result_holder[0] = func(*args, **kwargs)
        except Exception as exc:
            exc_holder[0] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.warning(
            "Timeout after %ds — function %s is still running in background",
            timeout, func.__name__,
        )
        raise TimeoutError(
            f"Function '{func.__name__}' exceeded {timeout}s timeout"
        )

    if exc_holder[0] is not None:
        raise exc_holder[0]

    return result_holder[0]


def with_timeout(seconds: int = 60) -> Callable:
    """
    Decorator that enforces a wall-clock time limit on a function.

    Args:
        seconds: Maximum allowed execution time.

    Example:
        @with_timeout(seconds=45)
        def call_risk_agent(state):
            return risk_agent.run(state)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return run_with_timeout(func, *args, timeout=seconds, **kwargs)
        return wrapper
    return decorator
