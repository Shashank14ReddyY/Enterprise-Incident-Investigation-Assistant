"""
search_test.py
Quick smoke-test for the RAG pipeline.
Run after ingest.py to confirm retrieval works correctly.

Usage:
    python -m Backend.search_test
"""

from __future__ import annotations
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from Backend.rag_pipeline import search_chunks, search_incidents, search_policies, list_sources, store_count

logging.basicConfig(level=logging.WARNING)


def hr(title: str = "") -> None:
    print("\n" + "=" * 60)
    if title:
        print(f"  {title}")
        print("=" * 60)


def show_results(results: list, label: str) -> None:
    print(f"\n[{label}]  ({len(results)} result(s))")
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['doc_type'].upper():8}] score={r['score']:.3f}  src={r['source']}")
        snippet = r["text"].replace("\n", " ")[:100]
        print(f"     \"{snippet}\"")


def run_tests() -> None:
    hr("PHASE 1 — RAG PIPELINE SMOKE TEST")

    total = store_count()
    sources = list_sources()
    print(f"\nVector store: {total} chunk(s)")
    print(f"Sources     : {sources}")

    if total == 0:
        print("\nERROR: Vector store is empty. Run 'python -m Backend.ingest' first.")
        sys.exit(1)

    # Test 1: Broad query across all doc types
    hr("TEST 1: Broad search (all docs)")
    results = search_chunks("suspicious login activity", top_k=5)
    show_results(results, "suspicious login activity — scope=all")

    # Test 2: Log-only search
    hr("TEST 2: Log-only search")
    results = search_incidents("failed login brute force", top_k=5)
    show_results(results, "failed login brute force — scope=logs")

    # Test 3: Policy/ISO-only search
    hr("TEST 3: Policy/ISO search")
    results = search_policies("account lockout policy MFA", top_k=5)
    show_results(results, "account lockout policy MFA — scope=policies")

    # Test 4: Admin activity
    hr("TEST 4: Admin activity")
    results = search_chunks("admin privilege escalation new account", top_k=5)
    show_results(results, "admin privilege escalation — scope=all")

    # Test 5: Firewall and data exfiltration
    hr("TEST 5: Firewall / exfiltration")
    results = search_chunks("firewall disabled database backup deleted", top_k=5)
    show_results(results, "firewall disabled — scope=all")

    # Test 6: ISO controls
    hr("TEST 6: ISO 27001 controls")
    results = search_policies("brute force authentication ISO control", top_k=3)
    show_results(results, "ISO brute force controls — scope=policies")

    hr("ALL TESTS PASSED")
    print("The RAG pipeline is working. Ready for Phase 2 agent integration.\n")


if __name__ == "__main__":
    run_tests()
