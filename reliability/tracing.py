"""
tracing.py
Lightweight distributed-style tracing for the agent pipeline.
Wraps each agent run with a Span that captures:
  - start_time, end_time, duration
  - status (completed / failed / skipped)
  - agent name and error message (if any)

Spans are written to the structured log and also returned so the
orchestrator can include them in the AgentState execution_trace.

Usage:
    from reliability.tracing import Tracer

    tracer = Tracer("Incident Agent")
    with tracer.span() as span:
        result = do_work()
    # span.to_dict() → {"agent": ..., "duration": ..., "status": ...}
"""

from __future__ import annotations
import time
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional, Generator

from reliability.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """One agent execution span."""
    agent: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration: float = 0.0
    status: str = "running"       # running | completed | failed | skipped
    error: Optional[str] = None

    def finish(self, status: str = "completed", error: Optional[str] = None) -> None:
        self.end_time = time.time()
        self.duration = round(self.end_time - self.start_time, 3)
        self.status = status
        self.error = error

    def to_dict(self) -> dict:
        d = {
            "agent": self.agent,
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "duration": self.duration,
            "status": self.status,
        }
        if self.error:
            d["error"] = self.error
        return d


class Tracer:
    """
    Creates and manages execution spans for one agent.

    Example:
        tracer = Tracer("Risk Agent")
        with tracer.span() as span:
            result = risky_call()
        print(span.to_dict())
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._slog = StructuredLogger(agent_name)
        self.spans: list[Span] = []

    @contextmanager
    def span(self) -> Generator[Span, None, None]:
        """
        Context manager that automatically records start/end times
        and logs the outcome to the structured log.

        Yields the active Span object; caller can read span.duration etc.
        after the with-block exits.
        """
        s = Span(agent=self.agent_name)
        self._slog.info(
            "span_start",
            f"{self.agent_name} span opened",
            data={"start_time": round(s.start_time, 3)},
        )
        try:
            yield s
            s.finish(status="completed")
            self._slog.agent_completed(
                duration=s.duration,
            )
        except Exception as exc:
            s.finish(status="failed", error=str(exc))
            self._slog.agent_failed(
                error=str(exc),
                duration=s.duration,
            )
            raise
        finally:
            self.spans.append(s)
            logger.debug(
                "Span closed — agent=%s duration=%.3fs status=%s",
                self.agent_name, s.duration, s.status,
            )

    def last_span(self) -> Optional[Span]:
        return self.spans[-1] if self.spans else None
