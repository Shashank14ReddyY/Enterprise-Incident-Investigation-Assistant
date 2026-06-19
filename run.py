"""
run.py
Top-level CLI entry point.

Usage:
    python run.py
    python run.py --query "Investigate failed login incidents"
    python run.py --query "Analyze the firewall disable event" --mode parallel
    python run.py --query "Summarize all incidents" --output report.md
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from agents.orchestrator import investigate
from agents.execution_log import print_trace, print_findings_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

EXAMPLE_QUERIES = [
    "Investigate failed login incidents and brute force attacks",
    "Analyze suspicious admin activity and privilege escalation",
    "Investigate the firewall disable and data exfiltration incident",
    "Identify insider threat activity and data leakage",
    "Investigate the API key exposure and fraudulent transactions",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise Incident Investigation Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\nExample queries:\n" + "\n".join(f"  {q}" for q in EXAMPLE_QUERIES),
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Investigation query (interactive prompt if not provided)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["sequential", "parallel"],
        default="sequential",
        help="Pipeline mode: sequential (default) or parallel",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Optional path to save the report (e.g. report.md)",
    )
    args = parser.parse_args()

    # ── Get query ─────────────────────────────────────────────────────────
    query = args.query
    if not query:
        print("\nEnterprise Incident Investigation Assistant")
        print("=" * 45)
        print("\nExample queries:")
        for i, q in enumerate(EXAMPLE_QUERIES, 1):
            print(f"  {i}. {q}")
        print()
        query = input("Enter your investigation query: ").strip()
        if not query:
            print("No query provided. Exiting.")
            sys.exit(1)

    # ── Run investigation ─────────────────────────────────────────────────
    print(f"\n🔍 Investigating: {query}")
    print(f"   Mode: {args.mode}\n")

    state = investigate(query, mode=args.mode)

    # ── Print results ─────────────────────────────────────────────────────
    print_trace(state)
    print_findings_summary(state)

    print("\n" + state.get("final_report", "[No report generated]"))

    # ── Save report if requested ──────────────────────────────────────────
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(state.get("final_report", ""), encoding="utf-8")
        print(f"\n📄 Report saved to: {out_path}")

    # ── Review comments ───────────────────────────────────────────────────
    comments = state.get("review_comments", [])
    if comments:
        print("\n📋 REVIEWER NOTES:")
        for comment in comments:
            print(f"  {comment}")


if __name__ == "__main__":
    main()
