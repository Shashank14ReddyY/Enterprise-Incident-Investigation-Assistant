"""
vector_store.py
Manages the vector store for all document chunks.
Uses TF-IDF + cosine similarity — fully local, no model downloads required.
Persists the index to disk via pickle so it survives between runs.
"""

from __future__ import annotations
import os
import pickle
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from Backend.chunker import Chunk

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.getenv("CHROMA_DB_PATH", "./vector_db")
INDEX_FILENAME = "tfidf_index.pkl"


class VectorStore:
    """
    TF-IDF based vector store with cosine similarity search.
    Persists to disk; re-ingestion is idempotent via source+index IDs.

    Usage:
        store = VectorStore()
        store.add_chunks(chunks)
        results = store.search("brute force login", top_k=5)
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path).resolve()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.db_path / INDEX_FILENAME

        # In-memory state
        self._ids: List[str] = []
        self._docs: List[str] = []
        self._metas: List[dict] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._matrix = None   # sparse TF-IDF matrix (n_docs × n_features)

        self._load()
        logger.info(
            "VectorStore ready — path=%s, docs=%d",
            self.db_path, len(self._docs),
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        data = {
            "ids": self._ids,
            "docs": self._docs,
            "metas": self._metas,
            "vectorizer": self._vectorizer,
            "matrix": self._matrix,
        }
        with open(self.index_path, "wb") as f:
            pickle.dump(data, f)

    def _load(self) -> None:
        if self.index_path.exists():
            try:
                with open(self.index_path, "rb") as f:
                    data = pickle.load(f)
                self._ids = data["ids"]
                self._docs = data["docs"]
                self._metas = data["metas"]
                self._vectorizer = data["vectorizer"]
                self._matrix = data["matrix"]
                logger.info("Loaded existing index with %d docs", len(self._docs))
            except Exception as exc:
                logger.warning("Could not load existing index (%s) — starting fresh.", exc)

    def _rebuild_index(self) -> None:
        """Refit the TF-IDF vectorizer on all stored documents."""
        if not self._docs:
            self._vectorizer = None
            self._matrix = None
            return
        self._vectorizer = TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(self._docs)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: List[Chunk]) -> int:
        """
        Add or update chunks. Idempotent — running twice won't duplicate.
        Returns the number of new/updated chunks.
        """
        if not chunks:
            return 0

        existing_ids = set(self._ids)
        added = 0

        for chunk in chunks:
            chunk_id = f"{chunk.source}::chunk_{chunk.chunk_index}"
            meta = {
                "source": chunk.source,
                "chunk_index": chunk.chunk_index,
                "doc_type": chunk.doc_type,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
            }

            if chunk_id in existing_ids:
                # Update in place
                idx = self._ids.index(chunk_id)
                self._docs[idx] = chunk.text
                self._metas[idx] = meta
            else:
                self._ids.append(chunk_id)
                self._docs.append(chunk.text)
                self._metas.append(meta)
                existing_ids.add(chunk_id)
                added += 1

        self._rebuild_index()
        self._save()
        logger.info("Added/updated %d chunk(s). Total: %d", added, len(self._docs))
        return added

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_type_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
    ) -> List[dict]:
        """
        Semantic similarity search using TF-IDF cosine similarity.

        Returns list of dicts with keys:
          text, source, doc_type, chunk_index, distance, score
        """
        if not self._docs or self._vectorizer is None:
            return []

        # Candidate indices (apply filters)
        candidates = list(range(len(self._docs)))
        if doc_type_filter:
            candidates = [i for i in candidates if self._metas[i].get("doc_type") == doc_type_filter]
        if source_filter:
            candidates = [i for i in candidates if self._metas[i].get("source") == source_filter]

        if not candidates:
            return []

        # Embed query and compute similarity against filtered candidates
        q_vec = self._vectorizer.transform([query])
        candidate_matrix = self._matrix[candidates]
        sims = cosine_similarity(q_vec, candidate_matrix)[0]

        # Sort by descending similarity
        top_n = min(top_k, len(candidates))
        top_indices = np.argsort(sims)[::-1][:top_n]

        results = []
        for local_idx in top_indices:
            global_idx = candidates[local_idx]
            score = float(sims[local_idx])
            results.append({
                "text": self._docs[global_idx],
                "source": self._metas[global_idx].get("source", ""),
                "doc_type": self._metas[global_idx].get("doc_type", ""),
                "chunk_index": self._metas[global_idx].get("chunk_index", -1),
                "distance": round(1 - score, 4),
                "score": round(score, 4),
            })

        return results

    def search_logs(self, query: str, top_k: int = 5) -> List[dict]:
        return self.search(query, top_k=top_k, doc_type_filter="log")

    def search_policies(self, query: str, top_k: int = 5) -> List[dict]:
        policy_results = self.search(query, top_k=top_k, doc_type_filter="policy")
        iso_results = self.search(query, top_k=top_k, doc_type_filter="iso")
        combined = policy_results + iso_results
        seen, deduped = set(), []
        for r in sorted(combined, key=lambda x: x["score"], reverse=True):
            if r["text"] not in seen:
                seen.add(r["text"])
                deduped.append(r)
        return deduped[:top_k]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def count(self) -> int:
        return len(self._docs)

    def clear(self) -> None:
        self._ids, self._docs, self._metas = [], [], []
        self._vectorizer, self._matrix = None, None
        if self.index_path.exists():
            self.index_path.unlink()
        logger.warning("VectorStore cleared.")

    def list_sources(self) -> List[str]:
        return sorted({m["source"] for m in self._metas})
