"""
chunker.py
Splits raw document text into overlapping chunks suitable for embedding.
Handles plain text and PDF-extracted text.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Chunk:
    """A single text chunk with metadata."""
    text: str
    source: str          # filename
    chunk_index: int
    start_char: int
    end_char: int
    doc_type: str = "unknown"   # "log", "policy", "iso", "unknown"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "doc_type": self.doc_type,
            **self.metadata,
        }


def _detect_doc_type(filename: str) -> str:
    """Infer document type from filename."""
    name = filename.lower()
    if "log" in name or name.endswith(".log"):
        return "log"
    if "policy" in name or "security" in name:
        return "policy"
    if "iso" in name or "27001" in name:
        return "iso"
    return "unknown"


def chunk_text(
    text: str,
    source: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[Chunk]:
    """
    Split text into overlapping character-level chunks.

    Args:
        text:        Full document text.
        source:      Filename or identifier for this document.
        chunk_size:  Target characters per chunk.
        overlap:     Characters of overlap between consecutive chunks.

    Returns:
        List of Chunk objects.
    """
    if not text or not text.strip():
        return []

    doc_type = _detect_doc_type(source)
    chunks: List[Chunk] = []
    start = 0
    idx = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # Extend to the next newline so we don't cut mid-sentence
        if end < text_len:
            newline_pos = text.find("\n", end)
            if newline_pos != -1 and newline_pos - end < 120:
                end = newline_pos + 1

        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            chunks.append(Chunk(
                text=chunk_text_str,
                source=source,
                chunk_index=idx,
                start_char=start,
                end_char=end,
                doc_type=doc_type,
            ))
            idx += 1

        # Slide window forward, keeping overlap
        start = end - overlap if end - overlap > start else end

    return chunks


def chunk_log_lines(
    text: str,
    source: str,
    lines_per_chunk: int = 5,
    overlap_lines: int = 1,
) -> List[Chunk]:
    """
    Chunk log files line-by-line rather than character-by-character.
    Preserves log event boundaries.

    Args:
        text:             Full log file content.
        source:           Filename.
        lines_per_chunk:  How many log lines per chunk.
        overlap_lines:    Lines of overlap between chunks.

    Returns:
        List of Chunk objects.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []

    chunks: List[Chunk] = []
    idx = 0
    i = 0

    while i < len(lines):
        batch = lines[i: i + lines_per_chunk]
        chunk_str = "\n".join(batch)
        start_char = text.find(batch[0])

        chunks.append(Chunk(
            text=chunk_str,
            source=source,
            chunk_index=idx,
            start_char=start_char,
            end_char=start_char + len(chunk_str),
            doc_type="log",
        ))
        idx += 1
        i += max(1, lines_per_chunk - overlap_lines)

    return chunks


def smart_chunk(
    text: str,
    source: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[Chunk]:
    """
    Auto-selects chunking strategy based on document type.
    Logs → line-based chunking.
    Everything else → character-based chunking.
    """
    doc_type = _detect_doc_type(source)
    if doc_type == "log":
        return chunk_log_lines(text, source, lines_per_chunk=6, overlap_lines=1)
    return chunk_text(text, source, chunk_size=chunk_size, overlap=overlap)
