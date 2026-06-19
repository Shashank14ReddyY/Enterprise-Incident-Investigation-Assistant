"""
document_loader.py
Loads incident logs and knowledge-base documents from disk.
Handles .txt and .pdf formats.
Returns raw text with source metadata for downstream chunking.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class RawDocument:
    """Raw document text plus metadata before chunking."""
    text: str
    source: str        # relative or absolute filename
    file_type: str     # "txt" | "pdf"
    size_bytes: int


def _load_txt(path: Path) -> str:
    """Load a plain-text or .log file."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _load_pdf(path: Path) -> str:
    """
    Extract text from a PDF using pypdf.
    Falls back gracefully if a page has no text layer.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required for PDF loading. Run: pip install pypdf")

    reader = PdfReader(str(path))
    pages: List[str] = []
    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(f"[Page {i + 1}]\n{page_text}")
        except Exception as exc:
            logger.warning("Could not extract text from page %d of %s: %s", i + 1, path.name, exc)

    return "\n\n".join(pages)


def load_file(path: str | Path) -> Optional[RawDocument]:
    """
    Load a single file.  Returns None if unsupported or unreadable.
    """
    path = Path(path)
    if not path.exists():
        logger.warning("File not found: %s", path)
        return None

    ext = path.suffix.lower()
    size = path.stat().st_size

    try:
        if ext in (".txt", ".log", ".md"):
            text = _load_txt(path)
            return RawDocument(text=text, source=path.name, file_type="txt", size_bytes=size)
        elif ext == ".pdf":
            text = _load_pdf(path)
            return RawDocument(text=text, source=path.name, file_type="pdf", size_bytes=size)
        else:
            logger.warning("Unsupported file type: %s (extension: %s)", path.name, ext)
            return None
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return None


def load_directory(directory: str | Path, recursive: bool = False) -> List[RawDocument]:
    """
    Load all supported files from a directory.

    Args:
        directory:  Path to scan.
        recursive:  If True, descend into subdirectories.

    Returns:
        List of RawDocument objects (failures are skipped with a warning).
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.warning("Not a directory: %s", directory)
        return []

    pattern = "**/*" if recursive else "*"
    docs: List[RawDocument] = []

    for path in sorted(directory.glob(pattern)):
        if path.is_file():
            doc = load_file(path)
            if doc:
                logger.info("Loaded %s (%d bytes)", doc.source, doc.size_bytes)
                docs.append(doc)

    logger.info("Loaded %d document(s) from %s", len(docs), directory)
    return docs


def load_knowledge_base(
    kb_dir: str | Path,
    logs_dir: str | Path,
) -> List[RawDocument]:
    """
    Convenience loader: combines KnowledgeBase + logs directories.

    Args:
        kb_dir:    Path to KnowledgeBase/ folder (PDFs, policy docs).
        logs_dir:  Path to logs/ folder (incident .txt log files).

    Returns:
        All loaded documents from both locations.
    """
    docs = []
    docs.extend(load_directory(kb_dir))
    docs.extend(load_directory(logs_dir))
    logger.info(
        "Total documents loaded — KnowledgeBase: %s, Logs: %s",
        kb_dir, logs_dir,
    )
    return docs
