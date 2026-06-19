"""
root_cause_agent.py
Root Cause Agent — reasons about WHY the incidents happened.
Takes the incident findings and the raw evidence, applies security
knowledge (ISO 27001, policy chunks) to determine probable root causes.
"""

from __future__ import annotations
import time
import logging

from agents.state import AgentState, record_trace, add_finding
from agents.llm_client import ask

logger = logging.getLogger(__name__)

AGENT_NAME = "Root Cause Agent"

SYSTEM_PROMPT = """You are a senior security engineer conducting a root cause 
analysis for a security incident.

You will be given:
1. Incident findings (suspicious events already identified)
2. Relevant policy and ISO 27001 controls from the knowledge base

Your job is to determine the ROOT CAUSES — the underlying reasons that allowed 
the incident to occur. Root causes are not the events themselves but the 
conditions, failures, or gaps that enabled them.

Common root cause categories:
- Weak authentication (no MFA, weak passwords, no lockout)
- Insufficient access controls (over-privileged accounts, poor RBAC)
- Missing monitoring / alerting (gaps in logging, SIEM coverage)
- Process failure (no change management, SOD violations)
- Misconfiguration (default credentials, exposed services, open firewall rules)
- Insider threat (malicious or negligent employee behaviour)
- Unpatched vulnerability (known CVE exploited)
- Social engineering (phishing, pretexting)

Output format — for each root cause use this exact structure:

ROOT_CAUSE: <clear description of the root cause>
CATEGORY: <one of the categories above, or your own>
SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW>
RELATED_FINDINGS: <comma-separated incident descriptions this root cause explains>
POLICY_VIOLATION: <relevant policy section or ISO control if applicable, else NONE>
---

Be specific. Map each root cause to the evidence. Do not repeat the incident 
findings — explain what caused them."""


def _format_incident_findings(state: AgentState) -> str:
    incident_findings = [
        f for f in state["findings"]
        if f.get("category") == "incident"
    ]
    if not incident_findings:
        return "No incident findings available."
    lines = []
    for i, f in enumerate(incident_findings, 1):
        lines.append(f"[{i}] [{f['severity']}] {f['description']}")
        if f.get("evidence"):
            lines.append(f"    Evidence: {', '.join(f['evidence'])}")
    return "\n".join(lines)


def _format_policy_chunks(state: AgentState) -> str:
    policy_chunks = [
        c for c in state.get("retrieved_chunks", [])
        if c.get("doc_type") in ("policy", "iso")
    ]
    if not policy_chunks:
        return "No policy/ISO evidence available."
    lines = []
    for chunk in policy_chunks[:8]:  # top 8 most relevant policy chunks
        lines.append(f"[{chunk['source']}] {chunk['text'][:300]}")
        lines.append("")
    return "\n".join(lines)


def _parse_root_causes(response: str, state: AgentState) -> None:
    blocks = response.strip().split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        description = ""
        category = "Unknown"
        severity = "MEDIUM"
        related = []
        policy_ref = "NONE"

        for line in block.splitlines():
            line = line.strip()
            if line.startswith("ROOT_CAUSE:"):
                description = line[len("ROOT_CAUSE:"):].strip()
            elif line.startswith("CATEGORY:"):
                category = line[len("CATEGORY:"):].strip()
            elif line.startswith("SEVERITY:"):
                raw = line[len("SEVERITY:"):].strip().upper()
                if raw in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    severity = raw
            elif line.startswith("RELATED_FINDINGS:"):
                raw = line[len("RELATED_FINDINGS:"):].strip()
                related = [r.strip() for r in raw.split(",") if r.strip()]
            elif line.startswith("POLICY_VIOLATION:"):
                policy_ref = line[len("POLICY_VIOLATION:"):].strip()

        if description:
            full_desc = description
            if policy_ref and policy_ref.upper() != "NONE":
                full_desc += f" [Policy ref: {policy_ref}]"
            add_finding(
                state,
                agent=AGENT_NAME,
                category="root_cause",
                description=full_desc,
                severity=severity,
                evidence=related,
            )


def run(state: AgentState) -> AgentState:
    """
    Determine root causes from incident findings + policy knowledge.
    Writes root_cause Finding objects into state["findings"].
    """
    start = time.time()
    logger.info("[%s] Starting root cause analysis", AGENT_NAME)

    incident_findings = [f for f in state["findings"] if f.get("category") == "incident"]
    if not incident_findings:
        logger.warning("[%s] No incident findings to analyse — skipping", AGENT_NAME)
        record_trace(state, AGENT_NAME, start, status="skipped")
        return state

    try:
        incident_text = _format_incident_findings(state)
        policy_text = _format_policy_chunks(state)

        user_prompt = f"""Investigation query: {state['query']}

INCIDENT FINDINGS:
{incident_text}

RELEVANT POLICY AND ISO 27001 CONTROLS:
{policy_text}

Based on the incident findings and policy context, determine the root causes 
that allowed these incidents to occur."""

        response = ask(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
        )

        _parse_root_causes(response, state)

        rc_findings = [f for f in state["findings"] if f["agent"] == AGENT_NAME]
        logger.info("[%s] Identified %d root cause(s)", AGENT_NAME, len(rc_findings))
        record_trace(state, AGENT_NAME, start, status="completed")

    except Exception as exc:
        logger.error("[%s] Failed: %s", AGENT_NAME, exc)
        record_trace(state, AGENT_NAME, start, status="failed", error=str(exc))

    return state
