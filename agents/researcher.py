"""
researcher.py
Research Agent — first agent in the pipeline.
Queries the RAG layer with multiple search angles, deduplicates results,
and stores the evidence in state["retrieved_chunks"].
"""

from __future__ import annotations
import time
import logging
from typing import List

from agents.state import AgentState, record_trace
from agents.llm_client import ask
from Backend.rag_pipeline import search_chunks

logger = logging.getLogger(__name__)

AGENT_NAME = "Researcher Agent"

SYSTEM_PROMPT = """You are a security research assistant helping to investigate 
enterprise security incidents. 

Given a user's investigation query, your job is to expand it into 3-5 specific 
search terms that will retrieve the most relevant evidence from an incident log 
and security policy database.

Respond with ONLY a Python list of search strings, one per line, no explanation.
Example output:
failed login attempts brute force
admin account privilege escalation
firewall configuration changes
audit log deletion tampering"""


def _expand_query(query: str) -> List[str]:
    """Use Claude to expand the user query into multiple search angles."""
    response = ask(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"Investigation query: {query}\n\nGenerate search terms:",
        max_tokens=256,
    )
    # Parse the response — one search term per non-empty line
    terms = [
        line.strip().strip("-•").strip()
        for line in response.strip().splitlines()
        if line.strip() and not line.strip().startswith("[")
        and not line.strip().startswith("]")
        and not line.strip().startswith("#")
    ]
    # Always include the original query itself
    if query not in terms:
        terms.insert(0, query)
    return terms[:6]  # cap at 6 searches


def _deduplicate(chunks: List[dict]) -> List[dict]:
    """Remove duplicate chunks by text content, keeping the highest score."""
    seen: dict[str, dict] = {}
    for chunk in chunks:
        key = chunk["text"]
        if key not in seen or chunk["score"] > seen[key]["score"]:
            seen[key] = chunk
    return sorted(seen.values(), key=lambda c: c["score"], reverse=True)


def run(state: AgentState) -> AgentState:
    """
    Retrieve evidence from the RAG layer.

    Expands the query into multiple search angles, searches both logs
    and policies, deduplicates, and stores the top chunks in state.
    """
    start = time.time()
    logger.info("[%s] Starting — query: %s", AGENT_NAME, state["query"])

    try:
        # 1. Expand the query into multiple search angles
        search_terms = _expand_query(state["query"])
        logger.info("[%s] Expanded to %d search terms: %s",
                    AGENT_NAME, len(search_terms), search_terms)

        # 2. Search logs and policies for each term
        all_chunks: List[dict] = []
        for term in search_terms:
            log_results = search_chunks(term, top_k=4, scope="logs")
            policy_results = search_chunks(term, top_k=3, scope="policies")
            all_chunks.extend(log_results)
            all_chunks.extend(policy_results)

        # 3. Deduplicate and keep top 20 most relevant chunks
        deduped = _deduplicate(all_chunks)[:20]
        state["retrieved_chunks"] = deduped

        logger.info("[%s] Retrieved %d unique chunks (from %d raw)",
                    AGENT_NAME, len(deduped), len(all_chunks))

        record_trace(state, AGENT_NAME, start, status="completed")

    except Exception as exc:
        logger.error("[%s] Failed: %s", AGENT_NAME, exc)
        record_trace(state, AGENT_NAME, start, status="failed", error=str(exc))

    return state
