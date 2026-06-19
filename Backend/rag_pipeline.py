"""
rag_pipeline.py
Public interface for the RAG layer.
Agents call search_chunks() — they never touch VectorStore or chunker directly.
"""

from __future__ import annotations
import logging
import os
from typing import List, Optional

from Backend.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Module-level singleton — initialised once, reused by all agents
_store: Optional[VectorStore] = None


def _get_store() -> VectorStore:
    """Return (or create) the shared VectorStore instance."""
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


# ---------------------------------------------------------------------------
# Core public function — this is what agents call
# ---------------------------------------------------------------------------

def search_chunks(
    query: str,
    top_k: int = 5,
    scope: str = "all",       # "all" | "logs" | "policies"
    source_filter: Optional[str] = None,
) -> List[dict]:
    """
    Retrieve the most relevant document chunks for a query.

    Args:
        query:         Natural-language search query from the calling agent.
        top_k:         Max number of results to return.
        scope:         Which documents to search:
                       - "all"      → logs + policy documents
                       - "logs"     → incident log files only
                       - "policies" → security policy + ISO documents only
        source_filter: Restrict to a specific filename (e.g. "Incident_Log_1.txt").

    Returns:
        List of dicts, each with:
          text        — chunk text
          source      — originating filename
          doc_type    — "log" | "policy" | "iso"
          chunk_index — position in source document
          score       — cosine similarity (0–1, higher = more relevant)
          distance    — raw cosine distance

    Example:
        >>> chunks = search_chunks("failed login brute force", top_k=5, scope="logs")
        >>> for c in chunks:
        ...     print(c["source"], c["score"], c["text"][:80])
    """
    store = _get_store()

    if store.count() == 0:
        logger.warning("Vector store is empty — run ingest.py first.")
        return []

    if scope == "logs":
        return store.search_logs(query, top_k=top_k)
    elif scope == "policies":
        return store.search_policies(query, top_k=top_k)
    else:
        return store.search(query, top_k=top_k, source_filter=source_filter)


def search_incidents(query: str, top_k: int = 5) -> List[dict]:
    """Alias: search only incident log chunks."""
    return search_chunks(query, top_k=top_k, scope="logs")


def search_policies(query: str, top_k: int = 5) -> List[dict]:
    """Alias: search only policy/ISO knowledge-base chunks."""
    return search_chunks(query, top_k=top_k, scope="policies")


def list_sources() -> List[str]:
    """Return all filenames currently in the vector store."""
    return _get_store().list_sources()


def store_count() -> int:
    """Return the total number of chunks in the store."""
    return _get_store().count()
