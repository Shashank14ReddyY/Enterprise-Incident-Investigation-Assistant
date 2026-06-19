"""
risk_agent.py
Risk Agent — evaluates the overall severity and business impact of the incident.
Considers the number of CRITICAL/HIGH findings, affected systems, data involved,
and relevant policy/ISO risk thresholds.
"""

from __future__ import annotations
import time
import logging

from agents.state import AgentState, record_trace, add_finding
from agents.llm_client import ask

logger = logging.getLogger(__name__)

AGENT_NAME = "Risk Agent"

SYSTEM_PROMPT = """You are a cybersecurity risk analyst evaluating the business 
impact and risk level of a security incident.

You will receive:
1. Incident findings (suspicious events)
2. Root cause findings
3. Relevant evidence from logs and policies

Your task is to produce a RISK ASSESSMENT covering:
- Overall incident severity (CRITICAL / HIGH / MEDIUM / LOW)
- Affected assets and systems
- Data at risk (type, estimated volume if known)
- Regulatory / compliance implications (GDPR, PCI-DSS, ISO 27001, etc.)
- Business impact (financial, reputational, operational)
- Immediate containment priority

Use this exact output format:

OVERALL_SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW>
AFFECTED_SYSTEMS: <comma-separated list of systems/hosts>
DATA_AT_RISK: <description of data types and volume, or NONE>
COMPLIANCE_IMPACT: <relevant regulations or standards implicated, or NONE>
BUSINESS_IMPACT: <brief description of operational/financial/reputational impact>
CONTAINMENT_PRIORITY: <IMMEDIATE|URGENT|SCHEDULED>
---
RISK_FINDING: <specific risk statement 1>
SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW>
RATIONALE: <why this risk level was assigned>
---
RISK_FINDING: <specific risk statement 2>
SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW>
RATIONALE: <why this risk level was assigned>
---

Add as many RISK_FINDING blocks as needed. Be precise about the risks —
distinguish between confirmed impact and potential impact."""


def _summarise_findings(state: AgentState) -> str:
    all_findings = state.get("findings", [])
    if not all_findings:
        return "No findings available."
    lines = []
    for f in all_findings:
        lines.append(
            f"[{f['agent']}] [{f['severity']}] [{f['category'].upper()}] {f['description']}"
        )
    return "\n".join(lines)


def _format_log_chunks(state: AgentState) -> str:
    log_chunks = [
        c for c in state.get("retrieved_chunks", [])
        if c.get("doc_type") == "log"
    ]
    lines = []
    for chunk in log_chunks[:6]:
        lines.append(f"[{chunk['source']}] {chunk['text'][:250]}")
    return "\n".join(lines) or "No log evidence available."


def _parse_risk_assessment(response: str, state: AgentState) -> None:
    """
    Parse the risk assessment response.
    Stores summary fields as a single HIGH-level finding plus individual risk findings.
    """
    # ── Parse summary block (before first ---) ──────────────────────────────
    parts = response.strip().split("---")
    summary_block = parts[0].strip()

    overall_severity = "HIGH"
    affected_systems = ""
    data_at_risk = ""
    compliance_impact = ""
    business_impact = ""
    containment_priority = "URGENT"

    for line in summary_block.splitlines():
        line = line.strip()
        if line.startswith("OVERALL_SEVERITY:"):
            raw = line[len("OVERALL_SEVERITY:"):].strip().upper()
            if raw in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                overall_severity = raw
        elif line.startswith("AFFECTED_SYSTEMS:"):
            affected_systems = line[len("AFFECTED_SYSTEMS:"):].strip()
        elif line.startswith("DATA_AT_RISK:"):
            data_at_risk = line[len("DATA_AT_RISK:"):].strip()
        elif line.startswith("COMPLIANCE_IMPACT:"):
            compliance_impact = line[len("COMPLIANCE_IMPACT:"):].strip()
        elif line.startswith("BUSINESS_IMPACT:"):
            business_impact = line[len("BUSINESS_IMPACT:"):].strip()
        elif line.startswith("CONTAINMENT_PRIORITY:"):
            containment_priority = line[len("CONTAINMENT_PRIORITY:"):].strip()

    summary_desc = (
        f"Overall severity: {overall_severity}. "
        f"Affected systems: {affected_systems}. "
        f"Data at risk: {data_at_risk}. "
        f"Compliance: {compliance_impact}. "
        f"Business impact: {business_impact}. "
        f"Containment: {containment_priority}."
    )
    add_finding(
        state,
        agent=AGENT_NAME,
        category="risk",
        description=summary_desc,
        severity=overall_severity,
        evidence=[affected_systems] if affected_systems else [],
    )

    # ── Parse individual risk findings ────────────────────────────────────
    for block in parts[1:]:
        block = block.strip()
        if not block:
            continue
        rf_desc = ""
        rf_severity = "MEDIUM"
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("RISK_FINDING:"):
                rf_desc = line[len("RISK_FINDING:"):].strip()
            elif line.startswith("SEVERITY:"):
                raw = line[len("SEVERITY:"):].strip().upper()
                if raw in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    rf_severity = raw
        if rf_desc:
            add_finding(
                state,
                agent=AGENT_NAME,
                category="risk",
                description=rf_desc,
                severity=rf_severity,
                evidence=[],
            )


def run(state: AgentState) -> AgentState:
    """
    Produce a risk assessment based on all findings so far.
    Writes risk Finding objects into state["findings"].
    """
    start = time.time()
    logger.info("[%s] Starting risk assessment", AGENT_NAME)

    all_findings = state.get("findings", [])
    if not all_findings:
        logger.warning("[%s] No findings available — skipping", AGENT_NAME)
        record_trace(state, AGENT_NAME, start, status="skipped")
        return state

    try:
        findings_text = _summarise_findings(state)
        log_text = _format_log_chunks(state)

        user_prompt = f"""Investigation query: {state['query']}

ALL FINDINGS SO FAR:
{findings_text}

SUPPORTING LOG EVIDENCE:
{log_text}

Produce a complete risk assessment for this incident."""

        response = ask(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
        )

        _parse_risk_assessment(response, state)

        risk_findings = [f for f in state["findings"] if f["agent"] == AGENT_NAME]
        logger.info("[%s] Produced %d risk finding(s)", AGENT_NAME, len(risk_findings))
        record_trace(state, AGENT_NAME, start, status="completed")

    except Exception as exc:
        logger.error("[%s] Failed: %s", AGENT_NAME, exc)
        record_trace(state, AGENT_NAME, start, status="failed", error=str(exc))

    return state
