"""
Frontend/app.py
Streamlit dashboard for the Enterprise Incident Investigation Assistant.

Sections:
  1. Sidebar       — query input, mode selector, run button, knowledge-base info
  2. Investigation — live agent progress → findings → risk summary → report
  3. Metrics       — per-agent timing bar chart + severity breakdown
  4. Execution Trace — full timeline table
  5. History       — previous runs loaded from agent_structured_logs.json

Run with:
    streamlit run Frontend/app.py
"""

from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Incident Investigation Assistant",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports after path setup ─────────────────────────────────────────────────
from agents.orchestrator import investigate
from agents.state import AgentState
from Backend.rag_pipeline import list_sources, store_count

# ── Constants ─────────────────────────────────────────────────────────────────
LOG_FILE = ROOT / "logs" / "agent_structured_logs.json"
LOGS_DIR = ROOT / "logs"

SEVERITY_COLORS = {
    "CRITICAL": "#dc2626",
    "HIGH":     "#ea580c",
    "MEDIUM":   "#d97706",
    "LOW":      "#16a34a",
    "INFO":     "#2563eb",
}

SEVERITY_BG = {
    "CRITICAL": "#fee2e2",
    "HIGH":     "#ffedd5",
    "MEDIUM":   "#fef3c7",
    "LOW":      "#dcfce7",
    "INFO":     "#dbeafe",
}

CATEGORY_ICONS = {
    "incident":   "🚨",
    "root_cause": "🔎",
    "risk":       "⚠️",
}

AGENT_ORDER = [
    "Researcher Agent",
    "Incident Agent",
    "Root Cause Agent",
    "Risk Agent",
    "Reviewer Agent",
    "Report Writer Agent",
]

EXAMPLE_QUERIES = [
    "Investigate failed login incidents and brute force attacks",
    "Analyze suspicious admin activity and privilege escalation",
    "Investigate the firewall disable and data exfiltration incident",
    "Identify insider threat activity and data leakage",
    "Investigate the API key exposure and fraudulent transactions",
    "Provide a full investigation across all incident logs",
]

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Severity badges */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
/* Finding cards */
.finding-card {
    border-left: 4px solid #94a3b8;
    background: #f8fafc;
    padding: 10px 14px;
    border-radius: 0 8px 8px 0;
    margin-bottom: 8px;
    font-size: 14px;
}
/* Metric cards */
.metric-box {
    background: #f1f5f9;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
}
.metric-number {
    font-size: 36px;
    font-weight: 800;
    line-height: 1;
}
.metric-label {
    font-size: 12px;
    color: #64748b;
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
/* Agent status row */
.agent-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    border-bottom: 1px solid #e2e8f0;
    font-size: 14px;
}
/* Timeline */
.timeline-bar {
    height: 8px;
    border-radius: 4px;
    background: #3b82f6;
    display: inline-block;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def severity_badge(severity: str) -> str:
    color = SEVERITY_COLORS.get(severity, "#64748b")
    bg    = SEVERITY_BG.get(severity, "#f1f5f9")
    return (
        f'<span class="badge" style="background:{bg};color:{color};">'
        f'{severity}</span>'
    )


def load_history() -> list[dict]:
    """Load previous investigation runs from the JSON log file."""
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def count_by_severity(findings: list) -> dict:
    counts: dict = {}
    for f in findings:
        sev = f.get("severity", "UNKNOWN")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def count_by_category(findings: list) -> dict:
    counts: dict = {}
    for f in findings:
        cat = f.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def get_overall_severity(findings: list) -> str:
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        if any(f.get("severity") == sev for f in findings):
            return sev
    return "INFO"


# ── Charts ────────────────────────────────────────────────────────────────────

def render_timing_chart(trace: list[dict]) -> None:
    """Horizontal bar chart of per-agent durations."""
    if not trace:
        st.info("No timing data available.")
        return

    # Sort by AGENT_ORDER for consistent display
    order_map = {name: i for i, name in enumerate(AGENT_ORDER)}
    sorted_trace = sorted(trace, key=lambda t: order_map.get(t["agent"], 99))

    agents    = [t["agent"].replace(" Agent", "") for t in sorted_trace]
    durations = [t["duration"] for t in sorted_trace]
    statuses  = [t["status"] for t in sorted_trace]

    bar_colors = []
    for s in statuses:
        if s == "completed":   bar_colors.append("#3b82f6")
        elif s == "skipped":   bar_colors.append("#94a3b8")
        else:                  bar_colors.append("#ef4444")

    fig = go.Figure(go.Bar(
        x=durations,
        y=agents,
        orientation="h",
        marker_color=bar_colors,
        text=[f"{d:.2f}s" for d in durations],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Duration: %{x:.3f}s<extra></extra>",
    ))
    fig.update_layout(
        title="Agent Execution Times",
        xaxis_title="Duration (seconds)",
        yaxis=dict(autorange="reversed"),
        height=300,
        margin=dict(l=0, r=60, t=40, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_severity_chart(findings: list) -> None:
    """Donut chart of findings by severity."""
    by_sev = count_by_severity(findings)
    if not by_sev:
        st.info("No findings to chart.")
        return

    labels = list(by_sev.keys())
    values = list(by_sev.values())
    colors = [SEVERITY_COLORS.get(l, "#94a3b8") for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker_colors=colors,
        textinfo="label+value",
        hovertemplate="<b>%{label}</b>: %{value} finding(s)<extra></extra>",
    ))
    fig.update_layout(
        title="Findings by Severity",
        height=280,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=True,
        legend=dict(orientation="v", x=1.0, y=0.5),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_category_chart(findings: list) -> None:
    """Horizontal bar chart of findings by category."""
    by_cat = count_by_category(findings)
    if not by_cat:
        return

    cat_colors = {"incident": "#ef4444", "root_cause": "#f97316", "risk": "#eab308"}
    labels = [f"{CATEGORY_ICONS.get(c, '')} {c.replace('_', ' ').title()}" for c in by_cat]
    values = list(by_cat.values())
    colors = [cat_colors.get(c, "#94a3b8") for c in by_cat]

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker_color=colors,
        text=values,
        textposition="outside",
    ))
    fig.update_layout(
        title="Findings by Category",
        height=200,
        margin=dict(l=0, r=40, t=40, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_timeline(trace: list[dict]) -> None:
    """Gantt-style timeline using Plotly."""
    if not trace:
        return

    order_map = {name: i for i, name in enumerate(AGENT_ORDER)}
    sorted_trace = sorted(trace, key=lambda t: order_map.get(t["agent"], 99))

    base = sorted_trace[0]["start_time"] if sorted_trace else 0

    fig = go.Figure()
    color_map = {"completed": "#3b82f6", "skipped": "#94a3b8", "failed": "#ef4444"}

    for t in sorted_trace:
        start_offset = t["start_time"] - base
        fig.add_trace(go.Bar(
            name=t["agent"],
            x=[t["duration"]],
            y=[t["agent"].replace(" Agent", "")],
            base=[start_offset],
            orientation="h",
            marker_color=color_map.get(t["status"], "#94a3b8"),
            text=f"{t['duration']:.2f}s",
            textposition="inside",
            hovertemplate=(
                f"<b>{t['agent']}</b><br>"
                f"Start: +{start_offset:.2f}s<br>"
                f"Duration: {t['duration']:.2f}s<br>"
                f"Status: {t['status']}<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.update_layout(
        title="Agent Execution Timeline (Gantt)",
        xaxis_title="Elapsed seconds from pipeline start",
        yaxis=dict(autorange="reversed"),
        barmode="overlay",
        height=320,
        margin=dict(l=0, r=20, t=40, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Section renderers ─────────────────────────────────────────────────────────

def render_summary_metrics(state: AgentState) -> None:
    """Top-row KPI cards."""
    findings   = state.get("findings", [])
    trace      = state.get("execution_trace", [])
    total_time = sum(t["duration"] for t in trace)
    overall    = get_overall_severity(findings)
    sev_color  = SEVERITY_COLORS.get(overall, "#64748b")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-number" style="color:{sev_color};">{overall}</div>
            <div class="metric-label">Overall Severity</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-number" style="color:#1e40af;">{len(findings)}</div>
            <div class="metric-label">Total Findings</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-number" style="color:#dc2626;">{critical_count}</div>
            <div class="metric-label">Critical</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        high_count = sum(1 for f in findings if f.get("severity") == "HIGH")
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-number" style="color:#ea580c;">{high_count}</div>
            <div class="metric-label">High</div>
        </div>""", unsafe_allow_html=True)
    with c5:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-number" style="color:#0f766e;">{total_time:.1f}s</div>
            <div class="metric-label">Pipeline Time</div>
        </div>""", unsafe_allow_html=True)


def render_findings(state: AgentState) -> None:
    """Tabbed view of findings by category."""
    findings = state.get("findings", [])
    if not findings:
        st.warning("No findings produced.")
        return

    incident_f  = [f for f in findings if f.get("category") == "incident"]
    rootcause_f = [f for f in findings if f.get("category") == "root_cause"]
    risk_f      = [f for f in findings if f.get("category") == "risk"]

    tab1, tab2, tab3 = st.tabs([
        f"🚨 Incident Findings ({len(incident_f)})",
        f"🔎 Root Causes ({len(rootcause_f)})",
        f"⚠️ Risk Assessment ({len(risk_f)})",
    ])

    def _render_finding_list(flist: list) -> None:
        for f in flist:
            sev   = f.get("severity", "INFO")
            color = SEVERITY_COLORS.get(sev, "#64748b")
            bg    = SEVERITY_BG.get(sev, "#f8fafc")
            desc  = f.get("description", "")
            evids = f.get("evidence", [])
            ev_str = ", ".join(evids) if evids else "—"

            st.markdown(f"""
            <div class="finding-card" style="border-left-color:{color};background:{bg};">
                {severity_badge(sev)}
                &nbsp;&nbsp;<strong>{desc}</strong>
                <br><small style="color:#64748b;">📄 {ev_str}</small>
            </div>""", unsafe_allow_html=True)

    with tab1:
        if incident_f:
            _render_finding_list(incident_f)
        else:
            st.info("No incident findings.")

    with tab2:
        if rootcause_f:
            _render_finding_list(rootcause_f)
        else:
            st.info("No root cause findings.")

    with tab3:
        if risk_f:
            _render_finding_list(risk_f)
        else:
            st.info("No risk findings.")


def render_review_comments(state: AgentState) -> None:
    """Display reviewer notes with colour-coded tags."""
    comments = state.get("review_comments", [])
    if not comments:
        st.info("No reviewer comments.")
        return

    tag_colors = {
        "[GAP]":       ("#dc2626", "#fee2e2"),
        "[FLAG]":      ("#ea580c", "#ffedd5"),
        "[SEVERITY]":  ("#d97706", "#fef3c7"),
        "[SUPPORTED]": ("#16a34a", "#dcfce7"),
        "[SUGGEST]":   ("#2563eb", "#dbeafe"),
    }

    for comment in comments:
        color, bg = "#64748b", "#f8fafc"
        for tag, (c, b) in tag_colors.items():
            if comment.startswith(tag):
                color, bg = c, b
                break
        st.markdown(
            f'<div style="background:{bg};border-left:3px solid {color};'
            f'padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:6px;'
            f'font-size:13px;">{comment}</div>',
            unsafe_allow_html=True,
        )


def render_execution_trace_table(state: AgentState) -> None:
    """Detailed trace table."""
    trace = state.get("execution_trace", [])
    if not trace:
        st.info("No trace data.")
        return

    order_map = {name: i for i, name in enumerate(AGENT_ORDER)}
    sorted_trace = sorted(trace, key=lambda t: order_map.get(t["agent"], 99))
    total = sum(t["duration"] for t in sorted_trace)

    header_cols = st.columns([3, 2, 2, 2, 2])
    for col, header in zip(header_cols, ["Agent", "Duration", "Status", "Start", "End"]):
        col.markdown(f"**{header}**")
    st.markdown("<hr style='margin:4px 0;'>", unsafe_allow_html=True)

    for t in sorted_trace:
        status_icon = {"completed": "✅", "skipped": "⏭️", "failed": "❌"}.get(t["status"], "❓")
        cols = st.columns([3, 2, 2, 2, 2])
        cols[0].write(t["agent"])
        cols[1].write(f"**{t['duration']:.3f}s**")
        cols[2].write(f"{status_icon} {t['status']}")
        cols[3].write(f"{t['start_time']:.2f}")
        cols[4].write(f"{t['end_time']:.2f}")
        if t.get("error"):
            st.error(f"↳ {t['error']}")

    st.markdown(f"<hr style='margin:4px 0;'>", unsafe_allow_html=True)
    st.markdown(f"**Total pipeline time: {total:.3f}s**")


def render_history() -> None:
    """Previous runs from agent_structured_logs.json."""
    history = load_history()
    if not history:
        st.info("No previous investigations found. Run your first investigation above.")
        return

    # Show most recent first
    for i, run in enumerate(reversed(history[-20:])):
        ts  = run.get("timestamp", "unknown")
        q   = run.get("query", "unknown query")
        tot = sum(t.get("duration", 0) for t in run.get("execution_trace", []))
        fs  = run.get("findings_summary", {})
        by_sev = fs.get("by_severity", {})
        sev_str = "  ".join(
            f"{sev}: {cnt}"
            for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
            if (cnt := by_sev.get(sev, 0)) > 0
        ) or "No findings"

        with st.expander(f"🕐 {ts[:19]}  |  {q[:70]}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Findings", fs.get("total", 0))
            c2.metric("Pipeline Time", f"{tot:.1f}s")
            c3.metric("Review Comments", run.get("review_comments_count", 0))
            st.caption(f"Severity breakdown: {sev_str}")

            trace = run.get("execution_trace", [])
            if trace:
                st.markdown("**Agent timings:**")
                for t in trace:
                    icon = "✅" if t["status"] == "completed" else "⏭️"
                    bar_width = min(int(t["duration"] * 30), 200)
                    st.markdown(
                        f'{icon} `{t["agent"]:<28}` '
                        f'`{"█" * max(1, int(t["duration"] * 8))}`  '
                        f'**{t["duration"]:.2f}s**'
                    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar() -> tuple[str, str]:
    """Renders sidebar. Returns (query, mode)."""
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/search--v1.png", width=60)
        st.title("Incident Investigation")
        st.caption("Enterprise Security AI Assistant")
        st.divider()

        # Knowledge base status
        st.subheader("📚 Knowledge Base")
        try:
            n_chunks = store_count()
            sources  = list_sources()
            if n_chunks == 0:
                st.error("⚠️ Vector store empty — run `python -m Backend.ingest` first.")
            else:
                st.success(f"✅ {n_chunks} chunks indexed")
                with st.expander(f"{len(sources)} source(s)"):
                    for s in sources:
                        st.caption(f"• {s}")
        except Exception as e:
            st.warning(f"Could not connect to vector store: {e}")

        st.divider()

        # Query input
        st.subheader("🔍 Investigation Query")
        example = st.selectbox(
            "Quick examples",
            ["(type your own below)"] + EXAMPLE_QUERIES,
            label_visibility="collapsed",
        )

        default_query = "" if example == "(type your own below)" else example
        query = st.text_area(
            "Query",
            value=default_query,
            height=100,
            placeholder="e.g. Investigate failed login incidents and brute force attacks",
            label_visibility="collapsed",
        )

        # Mode selector
        st.subheader("⚙️ Pipeline Mode")
        mode = st.radio(
            "Mode",
            options=["sequential", "parallel"],
            format_func=lambda m: {
                "sequential": "🔁 Sequential (easier to debug)",
                "parallel":   "⚡ Parallel (faster)",
            }[m],
            label_visibility="collapsed",
        )

        st.divider()

        # Run button
        run_clicked = st.button(
            "🚀 Run Investigation",
            type="primary",
            use_container_width=True,
            disabled=(not query.strip()),
        )

        # Available log files
        st.divider()
        st.subheader("📁 Log Files")
        log_files = sorted(LOGS_DIR.glob("Incident_Log_*.txt"))
        for lf in log_files:
            size_kb = lf.stat().st_size / 1024
            st.caption(f"• {lf.name}  ({size_kb:.1f} KB)")

        return query.strip(), mode, run_clicked


# ── Live progress display ─────────────────────────────────────────────────────

def run_with_progress(query: str, mode: str) -> AgentState:
    """
    Run the investigation with a live progress display.
    Shows each agent's status as the pipeline progresses.
    """
    progress_placeholder = st.empty()
    status_placeholder   = st.empty()

    agent_statuses = {agent: "⏳ waiting" for agent in AGENT_ORDER}

    def update_progress(current_agent: str, done: bool = False) -> None:
        with progress_placeholder.container():
            st.markdown("### 🔄 Pipeline Running…")
            for agent in AGENT_ORDER:
                if agent == current_agent and not done:
                    icon = "🔵"
                    label = "**running…**"
                elif agent_statuses[agent] == "✅ done":
                    icon = "✅"
                    label = "done"
                else:
                    icon = "⬜"
                    label = "waiting"
                st.markdown(f"{icon} `{agent}`  {label}")

    # Monkey-patch orchestrator to show per-step progress
    import agents.orchestrator as orch_module
    import agents.researcher as researcher_mod
    import agents.analyst as analyst_mod
    import agents.root_cause_agent as rc_mod
    import agents.risk_agent as risk_mod
    import agents.reviewer as reviewer_mod
    import agents.report_writer as rw_mod

    # Run the investigation — wrap each agent step with a UI update
    from agents.state import initial_state

    state = initial_state(query)

    steps = [
        ("Researcher Agent",    researcher_mod.run),
        ("Incident Agent",      analyst_mod.run),
        ("Root Cause Agent",    rc_mod.run),
        ("Risk Agent",          risk_mod.run),
        ("Reviewer Agent",      reviewer_mod.run),
        ("Report Writer Agent", rw_mod.run),
    ]

    if mode == "parallel":
        # Parallel: researcher first, then 3 in parallel
        update_progress("Researcher Agent")
        state = researcher_mod.run(state)
        agent_statuses["Researcher Agent"] = "✅ done"

        # Run middle 3 in parallel with thread pool
        import copy
        from concurrent.futures import ThreadPoolExecutor, as_completed

        parallel_steps = [
            ("Incident Agent",   analyst_mod.run),
            ("Root Cause Agent", rc_mod.run),
            ("Risk Agent",       risk_mod.run),
        ]
        update_progress("Incident Agent")

        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(fn, copy.deepcopy(state)): name
                for name, fn in parallel_steps
            }
            for future in as_completed(futures):
                agent_name = futures[future]
                result = future.result()
                results.append(result)
                agent_statuses[agent_name] = "✅ done"
                update_progress(agent_name)

        for result in results:
            state["findings"].extend(result.get("findings", []))
            state["execution_trace"].extend(result.get("execution_trace", []))

        # Sequential tail
        for name, fn in [("Reviewer Agent", reviewer_mod.run), ("Report Writer Agent", rw_mod.run)]:
            update_progress(name)
            state = fn(state)
            agent_statuses[name] = "✅ done"
            update_progress(name, done=True)

    else:
        # Sequential
        for name, fn in steps:
            update_progress(name)
            state = fn(state)
            agent_statuses[name] = "✅ done"

    # Save run log
    from agents.execution_log import save
    save(state)

    progress_placeholder.empty()
    status_placeholder.empty()
    return state


# ── Main app ──────────────────────────────────────────────────────────────────

def main() -> None:
    # Sidebar
    query, mode, run_clicked = render_sidebar()

    # Header
    st.title("🔍 Enterprise Incident Investigation Assistant")
    st.caption("AI-powered multi-agent security incident analysis")

    # ── Run investigation ──────────────────────────────────────────────────
    if run_clicked and query:
        st.session_state["last_state"] = None   # clear previous result
        st.session_state["last_query"] = query
        st.session_state["last_mode"]  = mode

        with st.spinner(""):
            try:
                state = run_with_progress(query, mode)
                st.session_state["last_state"] = state
                st.success("✅ Investigation complete!")
            except Exception as e:
                st.error(f"❌ Investigation failed: {e}")
                st.stop()

    # ── Results ────────────────────────────────────────────────────────────
    state: AgentState | None = st.session_state.get("last_state")

    if state:
        st.divider()

        # ── Summary metrics ───────────────────────────────────────────────
        st.subheader("📊 Incident Summary")
        render_summary_metrics(state)

        st.divider()

        # ── Charts row ────────────────────────────────────────────────────
        st.subheader("📈 Metrics")
        col_left, col_right = st.columns(2)
        with col_left:
            render_timing_chart(state.get("execution_trace", []))
        with col_right:
            render_severity_chart(state.get("findings", []))

        render_category_chart(state.get("findings", []))

        st.divider()

        # ── Findings tabs ─────────────────────────────────────────────────
        st.subheader("🔎 Findings")
        render_findings(state)

        st.divider()

        # ── Reviewer notes ────────────────────────────────────────────────
        st.subheader("📋 Reviewer Notes")
        render_review_comments(state)

        st.divider()

        # ── Final report ──────────────────────────────────────────────────
        st.subheader("📄 Incident Investigation Report")

        # Download button
        report_text = state.get("final_report", "")
        st.download_button(
            label="⬇️ Download Report (.txt)",
            data=report_text,
            file_name=f"incident_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=False,
        )

        with st.expander("📖 View Full Report", expanded=True):
            st.text(report_text)

        st.divider()

        # ── Execution trace ───────────────────────────────────────────────
        st.subheader("⏱️ Execution Trace")
        tab_table, tab_timeline = st.tabs(["📋 Table", "📊 Timeline"])
        with tab_table:
            render_execution_trace_table(state)
        with tab_timeline:
            render_timeline(state.get("execution_trace", []))

        # ── Raw evidence (expandable) ─────────────────────────────────────
        chunks = state.get("retrieved_chunks", [])
        if chunks:
            st.divider()
            with st.expander(f"🗂️ Raw Evidence Chunks ({len(chunks)} retrieved)"):
                for i, chunk in enumerate(chunks, 1):
                    st.markdown(
                        f"**[{i}]** `{chunk['source']}` | "
                        f"type: `{chunk['doc_type']}` | "
                        f"score: `{chunk['score']:.3f}`"
                    )
                    st.code(chunk["text"], language=None)

    else:
        # ── Landing state ─────────────────────────────────────────────────
        st.info(
            "👈  Enter an investigation query in the sidebar and click **Run Investigation** to begin."
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
            **🔐 What it investigates**
            - Brute force & credential attacks
            - Privilege escalation
            - Lateral movement & APT activity
            - Insider threats & data exfiltration
            - Secret exposure & API key breaches
            """)
        with col2:
            st.markdown("""
            **🤖 Agent pipeline**
            1. Researcher — retrieves evidence
            2. Incident Agent — finds events
            3. Root Cause Agent — explains why
            4. Risk Agent — assesses impact
            5. Reviewer — validates findings
            6. Report Writer — writes report
            """)
        with col3:
            st.markdown("""
            **📊 Dashboard features**
            - Live agent progress display
            - Severity & timing charts
            - Tabbed findings by category
            - Reviewer quality notes
            - Full report with download
            - Execution trace (table + Gantt)
            - Investigation history
            """)

    # ── History tab (always visible at bottom) ────────────────────────────
    st.divider()
    with st.expander("🕐 Investigation History", expanded=False):
        render_history()


if __name__ == "__main__":
    main()
