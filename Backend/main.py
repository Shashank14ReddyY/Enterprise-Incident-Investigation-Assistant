"""
Backend/main.py
Uvicorn entry point — starts the FastAPI server.

Usage:
    python -m Backend.main
    uvicorn Backend.main:app --reload --port 8000
"""

from __future__ import annotations
import logging
import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from Backend.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

app = create_app()

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() == "true"

    print(f"\n🚀 Incident Investigation API starting on http://{host}:{port}")
    print(f"   Docs: http://{host}:{port}/docs")
    print(f"   Mode: {'reload' if reload else 'production'}\n")

    uvicorn.run(
        "Backend.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
