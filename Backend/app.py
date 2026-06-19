"""
Backend/app.py
FastAPI application factory.
Creates and configures the app instance used by main.py (uvicorn).
"""

from __future__ import annotations
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Backend.api import router
from Backend.rag_pipeline import store_count

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hooks."""
    count = store_count()
    if count == 0:
        logger.warning(
            "Vector store is empty — run 'python -m Backend.ingest' before querying."
        )
    else:
        logger.info("Vector store ready — %d chunks loaded.", count)
    yield
    logger.info("API shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Incident Investigation API",
        description=(
            "AI-powered security incident investigation using a multi-agent pipeline. "
            "Analyses logs and knowledge-base documents to produce structured reports."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    # Allow the Streamlit frontend (Phase 4) and any local dev client
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app
