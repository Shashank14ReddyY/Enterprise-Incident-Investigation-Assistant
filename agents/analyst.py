"""
analyst.py
Incident Agent — analyses retrieved chunks to identify suspicious events.
Looks for: failed logins, privilege escalation, new admin accounts,
firewall changes, data exports, lateral movement, etc.
"""

from __future__ import annotations
import time
import logging

from agents.state import AgentState, record_trace, add_finding
from agents.llm_client import ask

logger = logging.getLogger(__name__)

AGENT_NAME = "Incident Agent"

SYSTEM_PROMPT = """You are an expert security incident analyst working in an 
enterprise Security Operations Centre (SOC).

Your job is to analyse evidence from incident logs and identify all suspicious 
or malicious events. For each finding, assess its severity.

Severity levels:
- CRITICAL: Active breach, data exfiltration, ransomware, system compromise
- HIGH: Privilege escalation, credential theft, firewall disabled, lateral movement
- MEDIUM: Multiple failed logins, unauthorised access attempts, policy violations
- LOW: Single failed login, minor anomaly, configuration drift

Output your findings as a structured list. For each finding use this exact format:

FINDING: <one-sentence description of the suspicious event>
SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW>
EVIDENCE: <comma-separated list of source files or specific log lines>
---

Be thorough. List every distinct suspicious event you find. Do not group 
unrelated events together — each event gets its own FINDING block."""


def _format_chunks(chunks: list) -> str:
    """Format retrieved chunks into a readable evidence block for the LLM."""
    if not chunks:
        return "No evidence retrieved."
    lines = []
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[{i}] Source: {chunk['source']} (score={chunk['score']:.3f})")
        lines.append(chunk["text"])
        lines.append("")
    return "\n".join(lines)


def _parse_findings(response: str, state: AgentState) -> None:
    """
    Parse the structured LLM response and write findings into state.
    Tolerates minor formatting variations.
    """
    blocks = response.strip().split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        description = ""
        severity = "MEDIUM"
        evidence = []

        for line in block.splitlines():
            line = line.strip()
            if line.startswith("FINDING:"):
                description = line[len("FINDING:"):].strip()
            elif line.startswith("SEVERITY:"):
                raw = line[len("SEVERITY:"):].strip().upper()
                if raw in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    severity = raw
            elif line.startswith("EVIDENCE:"):
                raw_ev = line[len("EVIDENCE:"):].strip()
                evidence = [e.strip() for e in raw_ev.split(",") if e.strip()]

        if description:
            add_finding(
                state,
                agent=AGENT_NAME,
                category="incident",
                description=description,
                severity=severity,
                evidence=evidence,
            )


def run(state: AgentState) -> AgentState:
    """
    Identify suspicious events in the retrieved evidence.
    Writes structured Finding objects into state["findings"].
    """
    start = time.time()
    logger.info("[%s] Starting analysis", AGENT_NAME)

    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        logger.warning("[%s] No evidence to analyse — skipping", AGENT_NAME)
        record_trace(state, AGENT_NAME, start, status="skipped")
        return state

    try:
        evidence_text = _format_chunks(chunks)

        user_prompt = f"""Investigation query: {state['query']}

Evidence retrieved from incident logs and security policies:

{evidence_text}

Identify all suspicious events in this evidence and list your findings."""

        response = ask(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
        )

        _parse_findings(response, state)

        incident_findings = [f for f in state["findings"] if f["agent"] == AGENT_NAME]
        logger.info("[%s] Identified %d incident finding(s)", AGENT_NAME, len(incident_findings))
        record_trace(state, AGENT_NAME, start, status="completed")

    except Exception as exc:
        logger.error("[%s] Failed: %s", AGENT_NAME, exc)
        record_trace(state, AGENT_NAME, start, status="failed", error=str(exc))

    return state
