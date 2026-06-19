"""
fallback_handler.py
Fallback chain for agent LLM calls.

Flow:
    Primary LLM call
        ↓ (failure / timeout)
    Retry (handled by retry_handler)
        ↓ (all retries exhausted)
    Fallback: RAG-only response
        ↓ (RAG also unavailable)
    Static degraded response

The RAG fallback constructs a minimal but useful response purely from
the retrieved chunks — no LLM call required — so the pipeline can still
produce output even during a complete API outage.
"""

from __future__ import annotations
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


# ── RAG-only fallback responses ──────────────────────────────────────────────

def _rag_fallback_incident(chunks: list, query: str) -> str:
    """Build a minimal incident finding from raw chunks when LLM is unavailable."""
    if not chunks:
        return (
            "FINDING: Unable to complete LLM analysis — API unavailable.\n"
            "SEVERITY: MEDIUM\n"
            "EVIDENCE: No evidence retrieved\n---"
        )
    log_chunks = [c for c in chunks if c.get("doc_type") == "log"]
    lines = [
        "FINDING: [FALLBACK] LLM unavailable — raw log evidence summary.\n"
        "SEVERITY: MEDIUM\n"
        f"EVIDENCE: {', '.join({c['source'] for c in log_chunks})}\n---"
    ]
    for c in log_chunks[:5]:
        lines.append(
            f"FINDING: Log activity detected in {c['source']}: "
            + c["text"][:120].replace("\n", " ")
            + "\nSEVERITY: MEDIUM\nEVIDENCE: " + c["source"] + "\n---"
        )
    return "\n".join(lines)


def _rag_fallback_root_cause(chunks: list, query: str) -> str:
    policy_chunks = [c for c in chunks if c.get("doc_type") in ("policy", "iso")]
    if not policy_chunks:
        return (
            "ROOT_CAUSE: [FALLBACK] LLM unavailable — root cause analysis incomplete.\n"
            "CATEGORY: Unknown\nSEVERITY: MEDIUM\nRELATED_FINDINGS: N/A\nPOLICY_VIOLATION: NONE\n---"
        )
    return (
        "ROOT_CAUSE: [FALLBACK] Root cause analysis requires manual review. "
        "Policy and ISO controls retrieved but LLM synthesis unavailable.\n"
        "CATEGORY: Process failure\nSEVERITY: MEDIUM\n"
        f"RELATED_FINDINGS: See log evidence\n"
        f"POLICY_VIOLATION: {policy_chunks[0]['source'] if policy_chunks else 'NONE'}\n---"
    )


def _rag_fallback_risk(chunks: list, query: str) -> str:
    return (
        "OVERALL_SEVERITY: HIGH\n"
        "AFFECTED_SYSTEMS: Unknown — manual review required\n"
        "DATA_AT_RISK: Unknown — LLM analysis unavailable\n"
        "COMPLIANCE_IMPACT: Review required\n"
        "BUSINESS_IMPACT: [FALLBACK] LLM unavailable — risk assessment incomplete. "
        "Manual review by security team required.\n"
        "CONTAINMENT_PRIORITY: URGENT\n---"
        "RISK_FINDING: [FALLBACK] Automated risk scoring unavailable. "
        "Treat as HIGH severity pending manual analysis.\n"
        "SEVERITY: HIGH\nRATIONALE: Conservative default during API outage.\n---"
    )


def _rag_fallback_report(state: dict) -> str:
    findings = state.get("findings", [])
    query = state.get("query", "Unknown")
    chunks = state.get("retrieved_chunks", [])
    sources = sorted({c["source"] for c in chunks}) if chunks else []

    findings_text = "\n".join(
        f"- [{f['severity']}] {f['description']}" for f in findings
    ) or "No findings produced."

    return f"""=================================================
INCIDENT INVESTIGATION REPORT  [DEGRADED MODE]
=================================================
NOTE: This report was generated in fallback mode because the LLM API
was unavailable. Content is based on retrieved evidence only.
Manual review by the security team is required.

USER QUERY
----------
{query}

EVIDENCE SOURCES
----------------
{', '.join(sources) if sources else 'None retrieved'}

FINDINGS (RAG-only)
-------------------
{findings_text}

RECOMMENDATIONS
---------------
1. [IMMEDIATE] Manually review all retrieved log evidence.
2. [IMMEDIATE] Engage SOC team for hands-on investigation.
3. [URGENT] Retry automated analysis once API is restored.

=================================================
END OF REPORT (DEGRADED)
================================================="""


# ── Fallback dispatcher ──────────────────────────────────────────────────────

FALLBACK_MAP = {
    "incident":    _rag_fallback_incident,
    "root_cause":  _rag_fallback_root_cause,
    "risk":        _rag_fallback_risk,
}


def with_fallback(
    primary_fn: Callable,
    fallback_type: str,
    *,
    chunks: Optional[list] = None,
    query: str = "",
    state: Optional[dict] = None,
) -> Any:
    """
    Execute primary_fn(); if it raises any exception, invoke the appropriate
    RAG-only fallback instead.

    Args:
        primary_fn:    The LLM call to attempt first (already wrapped with retry).
        fallback_type: One of "incident", "root_cause", "risk", "report".
        chunks:        Retrieved chunks to pass to the RAG fallback.
        query:         Original user query.
        state:         Full agent state (used by report fallback only).

    Returns:
        The return value of primary_fn on success, or the fallback string.
    """
    try:
        return primary_fn()
    except Exception as exc:
        logger.error(
            "Primary call failed (%s). Activating %s fallback. Error: %s",
            type(exc).__name__, fallback_type, exc,
        )
        chunks = chunks or []
        if fallback_type == "report" and state is not None:
            return _rag_fallback_report(state)
        fallback_fn = FALLBACK_MAP.get(fallback_type)
        if fallback_fn:
            return fallback_fn(chunks, query)
        return f"[FALLBACK] Analysis unavailable for '{fallback_type}'. Error: {exc}"
