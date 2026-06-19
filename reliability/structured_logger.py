"""
structured_logger.py
Emits structured JSON log records for every significant agent event.
Records are appended to logs/agent_structured_logs.jsonl (one JSON object per line).

Each record follows this schema:
{
    "timestamp": "2024-06-17T10:30:01.123456",
    "level":     "INFO" | "WARNING" | "ERROR" | "CRITICAL",
    "agent":     "Incident Agent",
    "event":     "finding_detected",
    "message":   "Detected 3 failed logins",
    "data":      { ... optional structured payload ... }
}

Usage:
    from reliability.structured_logger import StructuredLogger
    log = StructuredLogger("Incident Agent")
    log.info("finding_detected", "Detected brute force", data={"severity": "HIGH"})
    log.error("llm_call_failed", "API timeout", data={"attempt": 2})
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_py_logger = logging.getLogger(__name__)

LOGS_DIR = Path(os.getenv("LOGS_PATH", "./logs"))
JSONL_FILE = LOGS_DIR / "agent_structured_logs.jsonl"


def _write(record: dict) -> None:
    """Append one JSON record to the JSONL log file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(JSONL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except IOError as exc:
        _py_logger.warning("Could not write structured log: %s", exc)


class StructuredLogger:
    """
    Per-agent structured logger.
    Creates JSONL records and also forwards to the standard Python logger.
    """

    def __init__(self, agent_name: str):
        self.agent = agent_name
        self._py = logging.getLogger(f"agent.{agent_name.replace(' ', '_')}")

    def _emit(
        self,
        level: str,
        event: str,
        message: str,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        record = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "agent": self.agent,
            "event": event,
            "message": message,
        }
        if data:
            record["data"] = data
        _write(record)

        # Mirror to standard Python logging
        py_level = getattr(logging, level, logging.INFO)
        self._py.log(py_level, "[%s] %s — %s", event, message,
                     json.dumps(data) if data else "")

    def info(self, event: str, message: str, data: Optional[dict] = None) -> None:
        self._emit("INFO", event, message, data)

    def warning(self, event: str, message: str, data: Optional[dict] = None) -> None:
        self._emit("WARNING", event, message, data)

    def error(self, event: str, message: str, data: Optional[dict] = None) -> None:
        self._emit("ERROR", event, message, data)

    def critical(self, event: str, message: str, data: Optional[dict] = None) -> None:
        self._emit("CRITICAL", event, message, data)

    # ── Convenience helpers for common events ────────────────────────────

    def agent_started(self, query: str) -> None:
        self.info("agent_started", f"Starting {self.agent}", data={"query": query})

    def agent_completed(self, duration: float, findings_count: int = 0) -> None:
        self.info(
            "agent_completed",
            f"{self.agent} completed in {duration:.2f}s",
            data={"duration_seconds": round(duration, 3), "findings": findings_count},
        )

    def agent_failed(self, error: str, duration: float) -> None:
        self.error(
            "agent_failed",
            f"{self.agent} failed after {duration:.2f}s",
            data={"error": error, "duration_seconds": round(duration, 3)},
        )

    def finding_logged(self, severity: str, description: str) -> None:
        self.info(
            "finding_logged",
            f"Finding [{severity}]: {description[:100]}",
            data={"severity": severity},
        )

    def llm_call(self, model: str, prompt_chars: int) -> None:
        self.info(
            "llm_call",
            f"Calling {model}",
            data={"model": model, "prompt_chars": prompt_chars},
        )

    def fallback_activated(self, reason: str, fallback_type: str) -> None:
        self.warning(
            "fallback_activated",
            f"Fallback activated for {fallback_type}: {reason}",
            data={"fallback_type": fallback_type, "reason": reason},
        )

    def retry_attempt(self, attempt: int, max_attempts: int, error: str) -> None:
        self.warning(
            "retry_attempt",
            f"Retry {attempt}/{max_attempts}: {error}",
            data={"attempt": attempt, "max_attempts": max_attempts, "error": error},
        )
