"""
reviewer.py
Reviewer Agent — quality-gates the pipeline before report generation.
Checks for: missing evidence, contradictions, unsubstantiated severity ratings,
gaps in coverage, and missing remediation angles.
Writes review_comments into state.
"""

from __future__ import annotations
import time
import logging

from agents.state import AgentState, record_trace
from agents.llm_client import ask

logger = logging.getLogger(__name__)

AGENT_NAME = "Reviewer Agent"

SYSTEM_PROMPT = """You are a senior security manager performing a quality review 
of an automated incident investigation before it is delivered as a formal report.

You will receive the full set of findings from the investigation pipeline:
- Incident findings (suspicious events)
- Root cause findings
- Risk assessment findings
- Raw evidence (log chunks)

Your job is to:
1. Check that all major events in the evidence are covered by the findings
2. Flag any severity ratings that seem too high or too low
3. Identify any gaps — things in the evidence that were missed
4. Flag contradictions or unsupported claims
5. Note any important context that should be added to the report

Output a bullet-point review. Each point must start with one of:
  [GAP]       — something present in the evidence but missing from findings
  [SEVERITY]  — a severity rating that should be reconsidered
  [SUPPORTED] — a finding that is well-supported (positive confirmation)
  [FLAG]      — a contradiction, weak claim, or unsupported assertion
  [SUGGEST]   — a recommendation for the report writer to include

Be thorough but concise. Each bullet should be one clear sentence.
If the investigation is complete and accurate, say so explicitly."""


def _format_all_findings(state: AgentState) -> str:
    findings = state.get("findings", [])
    if not findings:
        return "No findings produced."
    lines = []
    for i, f in enumerate(findings, 1):
        lines.append(
            f"{i}. [{f['agent']}] [{f['severity']}] [{f['category'].upper()}] {f['description']}"
        )
    return "\n".join(lines)


def _format_evidence_summary(state: AgentState) -> str:
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        return "No evidence available."
    lines = []
    for chunk in chunks[:12]:
        lines.append(f"[{chunk['source']}] {chunk['text'][:200]}")
    return "\n".join(lines)


def run(state: AgentState) -> AgentState:
    """
    Review all findings for quality, gaps, and accuracy.
    Writes review comments into state["review_comments"].
    """
    start = time.time()
    logger.info("[%s] Starting review", AGENT_NAME)

    findings = state.get("findings", [])
    if not findings:
        state["review_comments"].append(
            "[GAP] No findings were produced by the pipeline — investigation is incomplete."
        )
        record_trace(state, AGENT_NAME, start, status="completed")
        return state

    try:
        findings_text = _format_all_findings(state)
        evidence_text = _format_evidence_summary(state)

        user_prompt = f"""Investigation query: {state['query']}

FINDINGS FROM ALL AGENTS:
{findings_text}

RAW EVIDENCE (log and policy chunks):
{evidence_text}

Review the findings above for completeness, accuracy, and quality."""

        response = ask(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1024,
        )

        # Store each non-empty line as a separate review comment
        comments = [
            line.strip()
            for line in response.strip().splitlines()
            if line.strip() and line.strip().startswith("[")
        ]
        if not comments:
            # Fallback: store the whole response as one comment
            comments = [response.strip()]

        state["review_comments"].extend(comments)
        logger.info("[%s] Produced %d review comment(s)", AGENT_NAME, len(comments))
        record_trace(state, AGENT_NAME, start, status="completed")

    except Exception as exc:
        logger.error("[%s] Failed: %s", AGENT_NAME, exc)
        record_trace(state, AGENT_NAME, start, status="failed", error=str(exc))

    return state
