"""
orchestrator.py
Runs the full agent pipeline in either sequential or parallel mode.

Sequential flow (default):
  Researcher → Incident → Root Cause → Risk → Reviewer → Report Writer

Parallel flow:
  Researcher → [Incident + Root Cause + Risk] (concurrent) → Reviewer → Report Writer

The parallel mode runs the three analysis agents simultaneously using
ThreadPoolExecutor, which cuts total latency by roughly 2-3× on
multi-core machines with network I/O as the bottleneck.
"""

from __future__ import annotations
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from agents.state import AgentState, initial_state
from agents import (
    researcher,
    analyst,
    root_cause_agent,
    risk_agent,
    reviewer,
    report_writer,
    execution_log,
)

logger = logging.getLogger(__name__)


# ── Sequential orchestration ────────────────────────────────────────────────

def run_sequential(query: str) -> AgentState:
    """
    Run the full pipeline step-by-step.
    Each agent receives the output of the previous one.
    Easiest to debug; use this during development.
    """
    logger.info("=" * 60)
    logger.info("SEQUENTIAL PIPELINE — query: %s", query)
    logger.info("=" * 60)

    state = initial_state(query)
    t0 = time.time()

    pipeline: list[Callable[[AgentState], AgentState]] = [
        researcher.run,
        analyst.run,
        root_cause_agent.run,
        risk_agent.run,
        reviewer.run,
        report_writer.run,
    ]

    for step in pipeline:
        agent_name = step.__module__.split(".")[-1]
        logger.info("▶ Running %s", agent_name)
        state = step(state)

    logger.info("Sequential pipeline complete in %.2fs", time.time() - t0)
    execution_log.save(state)
    return state


# ── Parallel orchestration ──────────────────────────────────────────────────

def _run_parallel_analysis(state: AgentState) -> AgentState:
    """
    Run Incident, Root Cause, and Risk agents concurrently.
    Each agent gets a shallow copy of state to avoid cross-writes during
    execution; results are merged back into the main state afterward.
    """
    import copy

    def _isolated_run(
        agent_fn: Callable[[AgentState], AgentState],
        base_state: AgentState,
    ) -> AgentState:
        """Run one agent on a copy of state and return the modified copy."""
        state_copy = copy.deepcopy(base_state)
        return agent_fn(state_copy)

    parallel_agents = [
        analyst.run,
        root_cause_agent.run,
        risk_agent.run,
    ]

    results: list[AgentState] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_isolated_run, fn, state): fn.__module__
            for fn in parallel_agents
        }
        for future in as_completed(futures):
            module = futures[future]
            try:
                result = future.result()
                results.append(result)
                logger.info("✓ Parallel agent finished: %s", module)
            except Exception as exc:
                logger.error("✗ Parallel agent failed: %s — %s", module, exc)

    # Merge findings and traces from all parallel results into main state
    for result in results:
        state["findings"].extend(result.get("findings", []))
        state["execution_trace"].extend(result.get("execution_trace", []))

    # Re-sort trace by start_time for a clean timeline
    state["execution_trace"].sort(key=lambda t: t["start_time"])

    return state


def run_parallel(query: str) -> AgentState:
    """
    Run the pipeline with Incident, Root Cause, and Risk agents in parallel.
    Researcher runs first (sequential), then all three analysis agents run
    concurrently, then Reviewer and Report Writer run sequentially.
    """
    logger.info("=" * 60)
    logger.info("PARALLEL PIPELINE — query: %s", query)
    logger.info("=" * 60)

    state = initial_state(query)
    t0 = time.time()

    # Stage 1: Researcher (must run first — populates retrieved_chunks)
    logger.info("▶ Stage 1: Researcher")
    state = researcher.run(state)

    # Stage 2: Parallel analysis
    logger.info("▶ Stage 2: Parallel analysis (Incident + Root Cause + Risk)")
    state = _run_parallel_analysis(state)

    # Stage 3: Reviewer (needs all findings)
    logger.info("▶ Stage 3: Reviewer")
    state = reviewer.run(state)

    # Stage 4: Report Writer (final output)
    logger.info("▶ Stage 4: Report Writer")
    state = report_writer.run(state)

    logger.info("Parallel pipeline complete in %.2fs", time.time() - t0)
    execution_log.save(state)
    return state


# ── Convenience entry point ─────────────────────────────────────────────────

def investigate(query: str, mode: str = "sequential") -> AgentState:
    """
    Public entry point called by run.py, the API, and the MCP server.

    Args:
        query:  The investigation question from the user.
        mode:   "sequential" (default, easier to debug) or
                "parallel" (faster for production use).

    Returns:
        Completed AgentState with final_report populated.
    """
    if mode == "parallel":
        return run_parallel(query)
    return run_sequential(query)
