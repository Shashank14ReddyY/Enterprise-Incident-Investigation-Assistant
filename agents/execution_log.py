"""
execution_log.py
Saves the per-run execution trace and structured agent findings to
logs/agent_structured_logs.json after each investigation.
Also provides helpers to print the trace to the terminal.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from agents.state import AgentState

logger = logging.getLogger(__name__)

LOGS_DIR = Path(os.getenv("LOGS_PATH", "./logs"))
LOG_FILE = LOGS_DIR / "agent_structured_logs.json"


def save(state: AgentState) -> None:
    """
    Append a complete run record to agent_structured_logs.json.
    Each run is one JSON object on its own line (JSONL-style within a list).
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Build the record
    record = {
        "timestamp": datetime.now().isoformat(),
        "query": state.get("query", ""),
        "execution_trace": state.get("execution_trace", []),
        "findings_summary": {
            "total": len(state.get("findings", [])),
            "by_severity": _count_by_severity(state),
            "by_category": _count_by_category(state),
        },
        "review_comments_count": len(state.get("review_comments", [])),
        "report_length_chars": len(state.get("final_report", "")),
    }

    # Load existing records, append, re-save
    records = []
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
        except (json.JSONDecodeError, IOError):
            records = []

    records.append(record)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    logger.info("Execution log saved → %s", LOG_FILE)


def print_trace(state: AgentState) -> None:
    """Print a formatted execution trace table to stdout."""
    trace = state.get("execution_trace", [])
    if not trace:
        print("No execution trace available.")
        return

    total = sum(t["duration"] for t in trace)
    print("\n" + "=" * 58)
    print(f"  EXECUTION TRACE")
    print("=" * 58)
    print(f"  {'Agent':<28} {'Duration':>8}  {'Status'}")
    print("-" * 58)
    for t in trace:
        status_icon = "✓" if t["status"] == "completed" else ("⚠" if t["status"] == "skipped" else "✗")
        print(f"  {t['agent']:<28} {t['duration']:>7.2f}s  {status_icon} {t['status']}")
        if t.get("error"):
            print(f"    └─ Error: {t['error']}")
    print("-" * 58)
    print(f"  {'TOTAL':<28} {total:>7.2f}s")
    print("=" * 58 + "\n")


def print_findings_summary(state: AgentState) -> None:
    """Print a quick findings summary to stdout."""
    findings = state.get("findings", [])
    print("\n" + "=" * 58)
    print("  FINDINGS SUMMARY")
    print("=" * 58)
    by_sev = _count_by_severity(state)
    by_cat = _count_by_category(state)
    print(f"  Total findings : {len(findings)}")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        count = by_sev.get(sev, 0)
        if count:
            bar = "█" * count
            print(f"  {sev:<10}: {count:>2}  {bar}")
    print(f"\n  By category:")
    for cat, count in by_cat.items():
        print(f"    {cat:<15}: {count}")
    print("=" * 58 + "\n")


def _count_by_severity(state: AgentState) -> dict:
    counts: dict = {}
    for f in state.get("findings", []):
        sev = f.get("severity", "UNKNOWN")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def _count_by_category(state: AgentState) -> dict:
    counts: dict = {}
    for f in state.get("findings", []):
        cat = f.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts
