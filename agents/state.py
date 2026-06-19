"""
state.py
Defines AgentState — the single shared object that flows through the entire
agent pipeline. Every agent reads from it and writes its findings back to it.
Nothing else is passed between agents.
"""

from __future__ import annotations
from typing import TypedDict, List, Optional
import time


class TraceEntry(TypedDict):
    agent: str
    start_time: float
    end_time: float
    duration: float
    status: str          # "completed" | "failed" | "skipped"
    error: Optional[str]


class Finding(TypedDict):
    agent: str
    category: str        # "incident" | "root_cause" | "risk"
    description: str
    severity: str        # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
    evidence: List[str]  # source filenames / log lines that support this


class AgentState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────────
    query: str                          # original user query

    # ── RAG evidence ─────────────────────────────────────────────────────────
    retrieved_chunks: List[dict]        # raw chunks from search_chunks()

    # ── Agent findings ───────────────────────────────────────────────────────
    findings: List[Finding]             # structured findings from all agents
    review_comments: List[str]          # reviewer's notes / flags

    # ── Report ───────────────────────────────────────────────────────────────
    final_report: str                   # markdown report from report_writer

    # ── Observability ────────────────────────────────────────────────────────
    execution_trace: List[TraceEntry]   # per-agent timing and status


def initial_state(query: str) -> AgentState:
    """Return a fresh AgentState for a new investigation."""
    return AgentState(
        query=query,
        retrieved_chunks=[],
        findings=[],
        review_comments=[],
        final_report="",
        execution_trace=[],
    )


def record_trace(
    state: AgentState,
    agent: str,
    start_time: float,
    status: str = "completed",
    error: Optional[str] = None,
) -> None:
    """Append a completed trace entry to state."""
    end_time = time.time()
    state["execution_trace"].append(TraceEntry(
        agent=agent,
        start_time=round(start_time, 3),
        end_time=round(end_time, 3),
        duration=round(end_time - start_time, 3),
        status=status,
        error=error,
    ))


def add_finding(
    state: AgentState,
    agent: str,
    category: str,
    description: str,
    severity: str,
    evidence: Optional[List[str]] = None,
) -> None:
    """Append a structured finding to state."""
    state["findings"].append(Finding(
        agent=agent,
        category=category,
        description=description,
        severity=severity,
        evidence=evidence or [],
    ))
