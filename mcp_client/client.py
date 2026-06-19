"""
mcp_client/client.py
HTTP client for the Incident Investigation FastAPI backend.
Can be used from scripts, notebooks, or the Streamlit frontend (Phase 4).

Usage:
    from mcp_client.client import InvestigationClient

    client = InvestigationClient(base_url="http://localhost:8000")

    # Start an investigation (non-blocking)
    job = client.start_investigation("Investigate failed login incidents")
    result = client.wait_for_result(job["job_id"])
    print(result["final_report"])

    # Or synchronously (blocks until done)
    report = client.investigate_sync("Analyze suspicious admin activity")
    print(report)
"""

from __future__ import annotations
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_POLL_INTERVAL = 3   # seconds between status polls
DEFAULT_TIMEOUT = 300       # max seconds to wait for a result


class InvestigationClient:
    """
    HTTP client for the Incident Investigation FastAPI backend.

    Args:
        base_url:  Base URL of the running FastAPI server.
        timeout:   httpx request timeout in seconds.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ── Health ────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """Check if the API server is reachable."""
        r = self._http.get("/health")
        r.raise_for_status()
        return r.json()

    def is_alive(self) -> bool:
        """Return True if the server responds to the health endpoint."""
        try:
            self.health()
            return True
        except Exception:
            return False

    # ── Investigation ─────────────────────────────────────────────────────

    def start_investigation(self, query: str, mode: str = "sequential") -> dict:
        """
        Start an investigation and return the job metadata immediately.
        Does not block — use wait_for_result() to poll for completion.

        Returns dict with keys: job_id, status, created_at, query, mode
        """
        r = self._http.post("/investigate", json={"query": query, "mode": mode})
        r.raise_for_status()
        job = r.json()
        logger.info("Investigation started — job_id=%s", job["job_id"])
        return job

    def get_status(self, job_id: str) -> dict:
        """
        Get the current status or result of an investigation job.
        Returns a JobStatus dict while pending/running,
        or a full InvestigationResult dict when completed.
        """
        r = self._http.get(f"/investigate/{job_id}")
        r.raise_for_status()
        return r.json()

    def wait_for_result(
        self,
        job_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        verbose: bool = True,
    ) -> dict:
        """
        Poll until the investigation job completes and return the full result.

        Args:
            job_id:        Job ID returned by start_investigation().
            poll_interval: Seconds between status checks.
            timeout:       Maximum total seconds to wait.
            verbose:       Print progress dots to stdout.

        Returns:
            InvestigationResult dict with final_report, findings, trace, etc.

        Raises:
            TimeoutError: If the job doesn't complete within `timeout` seconds.
            RuntimeError: If the job fails on the server side.
        """
        start = time.time()
        if verbose:
            print(f"Waiting for job {job_id}", end="", flush=True)

        while True:
            elapsed = time.time() - start
            if elapsed > timeout:
                raise TimeoutError(
                    f"Job {job_id} did not complete within {timeout}s"
                )

            result = self.get_status(job_id)
            status = result.get("status")

            if status == "completed":
                if verbose:
                    print(f" done ({elapsed:.0f}s)")
                return result
            elif status == "failed":
                raise RuntimeError(f"Investigation job failed: {result}")

            if verbose:
                print(".", end="", flush=True)
            time.sleep(poll_interval)

    def investigate_sync(
        self,
        query: str,
        mode: str = "sequential",
        verbose: bool = True,
    ) -> str:
        """
        Convenience: start an investigation and block until the report is ready.

        Returns the final_report string.
        """
        job = self.start_investigation(query, mode=mode)
        result = self.wait_for_result(job["job_id"], verbose=verbose)
        return result.get("final_report", "")

    # ── Knowledge base ────────────────────────────────────────────────────

    def list_sources(self) -> list[str]:
        """Return all document sources in the vector store."""
        r = self._http.get("/sources")
        r.raise_for_status()
        return r.json().get("sources", [])

    def list_logs(self) -> list[dict]:
        """Return metadata for all incident log files."""
        r = self._http.get("/logs")
        r.raise_for_status()
        return r.json().get("logs", [])

    def search(self, query: str, top_k: int = 5, scope: str = "all") -> list[dict]:
        """
        Run a raw RAG search and return matching chunks.

        Args:
            query:  Search query string.
            top_k:  Max results to return.
            scope:  "all" | "logs" | "policies"
        """
        r = self._http.post("/search", json={"query": query, "top_k": top_k, "scope": scope})
        r.raise_for_status()
        return r.json().get("results", [])

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ── Quick CLI test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    query = sys.argv[2] if len(sys.argv) > 2 else "Investigate failed login incidents"

    print(f"Connecting to {base_url}…")
    with InvestigationClient(base_url) as client:
        if not client.is_alive():
            print("ERROR: API server not reachable. Start it with: python -m Backend.main")
            sys.exit(1)

        print(f"✓ Server alive\n")
        print(f"Sources in store: {client.list_sources()}\n")
        print(f"Log files: {[l['filename'] for l in client.list_logs()]}\n")

        print(f"Starting investigation: '{query}'")
        report = client.investigate_sync(query, mode="sequential")
        print("\n" + report)
