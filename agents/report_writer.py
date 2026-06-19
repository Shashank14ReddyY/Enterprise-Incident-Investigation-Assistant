"""
report_writer.py
Report Writer Agent — the final agent in the pipeline.
Synthesises all findings, root causes, risk assessments, and review comments
into a professionally structured Incident Investigation Report.
"""

from __future__ import annotations
import time
import logging
from datetime import datetime

from agents.state import AgentState, record_trace
from agents.llm_client import ask

logger = logging.getLogger(__name__)

AGENT_NAME = "Report Writer Agent"

SYSTEM_PROMPT = """You are a senior cybersecurity analyst writing a formal 
Incident Investigation Report for enterprise stakeholders.

The report must be:
- Professional and precise
- Written for both technical and non-technical readers
- Evidence-based (cite sources where relevant)
- Actionable (recommendations must be specific and prioritised)

Use this exact report structure:

=================================================
INCIDENT INVESTIGATION REPORT
=================================================
Date: <today's date>
Prepared by: Enterprise Incident Investigation Assistant
Classification: CONFIDENTIAL

EXECUTIVE SUMMARY
-----------------
<2-3 sentence summary of what happened, the severity, and the top action required>

USER QUERY
----------
<restate the original query>

EVIDENCE SOURCES
----------------
<list the log files and documents used as evidence>

INCIDENT FINDINGS
-----------------
<numbered list of all confirmed suspicious events with severity tags>

ROOT CAUSE ANALYSIS
-------------------
<numbered list of root causes with explanation of how they enabled the incident>

RISK ASSESSMENT
---------------
Overall Severity: <CRITICAL|HIGH|MEDIUM|LOW>
<key risk findings with business impact context>

REVIEW NOTES
------------
<reviewer comments — gaps, flags, and confirmations>

RECOMMENDATIONS
---------------
<numbered, prioritised remediation steps — immediate first, then short-term, then long-term>
Each recommendation should:
  - State the action clearly
  - Reference the finding or root cause it addresses
  - Suggest an owner (e.g. SOC, IT Operations, HR, Development Team)

EXECUTION SUMMARY
-----------------
<list each agent with its duration in seconds>

=================================================
END OF REPORT
=================================================

Write the complete report now. Be thorough."""


def _gather_report_data(state: AgentState) -> str:
    """Compile all state data into a structured prompt for the report writer."""
    findings = state.get("findings", [])
    review_comments = state.get("review_comments", [])
    chunks = state.get("retrieved_chunks", [])
    trace = state.get("execution_trace", [])

    # Categorise findings
    incident_findings = [f for f in findings if f.get("category") == "incident"]
    root_causes = [f for f in findings if f.get("category") == "root_cause"]
    risk_findings = [f for f in findings if f.get("category") == "risk"]

    def fmt_findings(lst):
        if not lst:
            return "None identified."
        return "\n".join(
            f"- [{f['severity']}] {f['description']}" +
            (f"\n  Sources: {', '.join(f['evidence'])}" if f.get('evidence') else "")
            for f in lst
        )

    sources = sorted({c["source"] for c in chunks}) if chunks else []

    trace_text = "\n".join(
        f"- {t['agent']}: {t['duration']}s ({t['status']})"
        for t in trace
    ) or "No trace data."

    review_text = "\n".join(f"- {c}" for c in review_comments) or "No review comments."

    return f"""USER QUERY: {state['query']}

DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

EVIDENCE SOURCES: {', '.join(sources) if sources else 'None'}

INCIDENT FINDINGS:
{fmt_findings(incident_findings)}

ROOT CAUSE FINDINGS:
{fmt_findings(root_causes)}

RISK ASSESSMENT FINDINGS:
{fmt_findings(risk_findings)}

REVIEWER COMMENTS:
{review_text}

AGENT EXECUTION TRACE:
{trace_text}"""


def run(state: AgentState) -> AgentState:
    """
    Generate the final incident investigation report.
    Writes the formatted report string into state["final_report"].
    """
    start = time.time()
    logger.info("[%s] Writing final report", AGENT_NAME)

    try:
        report_data = _gather_report_data(state)

        response = ask(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=f"Generate the full incident investigation report from this data:\n\n{report_data}",
            max_tokens=4096,
        )

        state["final_report"] = response
        logger.info("[%s] Report written (%d chars)", AGENT_NAME, len(response))
        record_trace(state, AGENT_NAME, start, status="completed")

    except Exception as exc:
        logger.error("[%s] Failed: %s", AGENT_NAME, exc)
        state["final_report"] = f"[ERROR] Report generation failed: {exc}"
        record_trace(state, AGENT_NAME, start, status="failed", error=str(exc))

    return state
