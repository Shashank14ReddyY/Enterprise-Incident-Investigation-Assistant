"""
Backend/api.py
All FastAPI route handlers for the Incident Investigation API.

Endpoints:
  POST /investigate          — run a full investigation (sequential or parallel)
  GET  /investigate/{job_id} — retrieve a completed investigation result
  GET  /sources              — list all ingested document sources
  GET  /logs                 — list available incident log files
  POST /search               — raw RAG search (for debugging / MCP)
  GET  /health               — liveness check
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from agents.orchestrator import investigate
from agents.state import AgentState
from Backend.rag_pipeline import search_chunks, list_sources
from Backend.document_loader import load_directory
import os
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory job store (replace with Redis / DB in production)
_jobs: dict[str, dict] = {}


# ── Request / Response models ────────────────────────────────────────────────

class InvestigateRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="The investigation question, e.g. 'Investigate failed login incidents'",
        example="Investigate suspicious admin activity and privilege escalation",
    )
    mode: str = Field(
        default="sequential",
        description="Pipeline mode: 'sequential' (default) or 'parallel'",
    )


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    scope: str = Field(default="all", description="'all' | 'logs' | 'policies'")


class JobStatus(BaseModel):
    job_id: str
    status: str           # "pending" | "running" | "completed" | "failed"
    created_at: str
    completed_at: Optional[str] = None
    query: str
    mode: str


class InvestigationResult(BaseModel):
    job_id: str
    status: str
    query: str
    final_report: str
    findings_count: int
    review_comments: list[str]
    execution_trace: list[dict]
    created_at: str
    completed_at: Optional[str] = None


# ── Background job runner ────────────────────────────────────────────────────

def _run_investigation_job(job_id: str, query: str, mode: str) -> None:
    """Run investigation in background and store result in _jobs."""
    _jobs[job_id]["status"] = "running"
    try:
        state: AgentState = investigate(query, mode=mode)
        _jobs[job_id].update({
            "status": "completed",
            "state": state,
            "completed_at": datetime.now().isoformat(),
        })
        logger.info("Job %s completed — %d findings", job_id, len(state["findings"]))
    except Exception as exc:
        _jobs[job_id].update({
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.now().isoformat(),
        })
        logger.error("Job %s failed: %s", job_id, exc)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/health", tags=["System"])
def health_check():
    """Liveness check — returns 200 when the API is up."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@router.post("/investigate", response_model=JobStatus, status_code=202, tags=["Investigation"])
def start_investigation(
    request: InvestigateRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start an incident investigation.
    Returns a job_id immediately; poll GET /investigate/{job_id} for results.
    """
    if request.mode not in ("sequential", "parallel"):
        raise HTTPException(status_code=400, detail="mode must be 'sequential' or 'parallel'")

    job_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "query": request.query,
        "mode": request.mode,
        "created_at": created_at,
        "completed_at": None,
        "state": None,
        "error": None,
    }

    background_tasks.add_task(_run_investigation_job, job_id, request.query, request.mode)
    logger.info("Investigation job %s queued — query: %s", job_id, request.query)

    return JobStatus(
        job_id=job_id,
        status="pending",
        created_at=created_at,
        query=request.query,
        mode=request.mode,
    )


@router.get("/investigate/{job_id}", tags=["Investigation"])
def get_investigation(job_id: str):
    """
    Poll the status or retrieve the result of an investigation job.
    Returns status while pending/running, full result when completed.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    job = _jobs[job_id]

    if job["status"] in ("pending", "running"):
        return JobStatus(
            job_id=job_id,
            status=job["status"],
            created_at=job["created_at"],
            query=job["query"],
            mode=job["mode"],
        )

    if job["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Investigation failed: {job.get('error', 'unknown error')}",
        )

    state: AgentState = job["state"]
    return InvestigationResult(
        job_id=job_id,
        status="completed",
        query=job["query"],
        final_report=state.get("final_report", ""),
        findings_count=len(state.get("findings", [])),
        review_comments=state.get("review_comments", []),
        execution_trace=state.get("execution_trace", []),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
    )


@router.get("/sources", tags=["Knowledge Base"])
def get_sources():
    """List all document sources currently in the vector store."""
    sources = list_sources()
    return {"sources": sources, "count": len(sources)}


@router.get("/logs", tags=["Knowledge Base"])
def list_logs():
    """List available incident log files from the logs/ directory."""
    logs_dir = Path(os.getenv("LOGS_PATH", "./logs"))
    log_files = []
    if logs_dir.is_dir():
        for f in sorted(logs_dir.glob("*.txt")):
            stat = f.stat()
            log_files.append({
                "filename": f.name,
                "size_bytes": stat.st_size,
                "lines": sum(1 for _ in open(f, encoding="utf-8", errors="replace")),
            })
    return {"logs": log_files, "count": len(log_files)}


@router.post("/search", tags=["Knowledge Base"])
def search(request: SearchRequest):
    """
    Raw RAG search — returns the top-k most relevant document chunks.
    Useful for debugging retrieval quality and for MCP tool integration.
    """
    results = search_chunks(request.query, top_k=request.top_k, scope=request.scope)
    return {
        "query": request.query,
        "scope": request.scope,
        "results": results,
        "count": len(results),
    }
