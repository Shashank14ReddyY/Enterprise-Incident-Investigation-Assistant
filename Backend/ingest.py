"""
ingest.py
One-time (and idempotent) ingestion script.
Run this to populate the ChromaDB vector store from KnowledgeBase/ and logs/.

Usage:
    python -m Backend.ingest
    python -m Backend.ingest --clear   # wipe store first, then re-ingest
"""

from __future__ import annotations
import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from Backend.document_loader import load_knowledge_base
from Backend.chunker import smart_chunk
from Backend.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest")


def ingest(clear: bool = False) -> None:
    BASE = Path(__file__).resolve().parent.parent
    KB_DIR = BASE / os.getenv("KNOWLEDGE_BASE_PATH", "KnowledgeBase")
    LOGS_DIR = BASE / os.getenv("LOGS_PATH", "logs")
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 500))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 50))

    logger.info("=" * 55)
    logger.info("INCIDENT INVESTIGATION — INGESTION PIPELINE")
    logger.info("=" * 55)
    logger.info("KnowledgeBase : %s", KB_DIR)
    logger.info("Logs          : %s", LOGS_DIR)

    # 1. Load raw documents
    t0 = time.time()
    docs = load_knowledge_base(kb_dir=KB_DIR, logs_dir=LOGS_DIR)
    if not docs:
        logger.error("No documents found. Check your KB_DIR and LOGS_DIR paths.")
        sys.exit(1)
    logger.info("Loaded %d document(s) in %.2fs", len(docs), time.time() - t0)

    # 2. Chunk
    t1 = time.time()
    all_chunks = []
    for doc in docs:
        chunks = smart_chunk(doc.text, doc.source, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        logger.info("  %s → %d chunk(s)", doc.source, len(chunks))
        all_chunks.extend(chunks)
    logger.info("Total chunks: %d  (%.2fs)", len(all_chunks), time.time() - t1)

    # 3. Embed + store
    t2 = time.time()
    store = VectorStore()
    if clear:
        logger.warning("--clear flag set: wiping existing collection.")
        store.clear()

    n = store.add_chunks(all_chunks)
    logger.info("Upserted %d chunk(s) in %.2fs", n, time.time() - t2)

    # 4. Summary
    logger.info("-" * 55)
    logger.info("Vector store now contains %d chunk(s)", store.count())
    logger.info("Sources: %s", store.list_sources())
    logger.info("Total time: %.2fs", time.time() - t0)
    logger.info("=" * 55)
    logger.info("Ingestion complete. Ready for agent queries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documents into ChromaDB.")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the vector store before ingesting (re-ingest from scratch).",
    )
    args = parser.parse_args()
    ingest(clear=args.clear)
