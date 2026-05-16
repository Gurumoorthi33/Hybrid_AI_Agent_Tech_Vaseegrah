"""
memory/vector_store.py
Multi-tenant FAISS vector store.

Each VectorStore instance is scoped to ONE index file (one path pair).
The retriever_agent creates two instances per request:
  - default_vs  → company knowledge (vaseegrah_veda.txt)  [always loaded]
  - customer_vs → customer-uploaded RAG files             [loaded if exists]

Results from both are merged and re-ranked before returning to the agent.
"""

import os
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
from config.settings import EMBED_MODEL, TOP_K

# Shared model singleton — loaded once, reused across all instances
_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


class VectorStore:
    """
    FAISS-backed store for one index (one tenant or the default KB).
    index_path / docs_path  — file locations for this store.
    label                   — shown in logs ("default" / "customer:<id>")
    """

    def __init__(self, index_path: str, docs_path: str, label: str = "store"):
        self._index_path = index_path
        self._docs_path  = docs_path
        self._label      = label
        self._index: faiss.Index | None = None
        self._docs: list[str] = []
        self._load()

    # ── persistence ──────────────────────────────────────────────

    def _load(self):
        if os.path.exists(self._index_path) and os.path.exists(self._docs_path):
            try:
                self._index = faiss.read_index(self._index_path)
                with open(self._docs_path, "rb") as f:
                    self._docs = pickle.load(f)
                print(f"✅ VectorStore [{self._label}] loaded: {len(self._docs)} docs")
            except Exception as e:
                print(f"⚠️  VectorStore [{self._label}] load failed: {e}")

    def _save(self):
        os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
        faiss.write_index(self._index, self._index_path)
        with open(self._docs_path, "wb") as f:
            pickle.dump(self._docs, f)

    # ── write ─────────────────────────────────────────────────────

    def add_documents(self, texts: list[str]):
        model = _get_model()
        embeddings = model.encode(texts, show_progress_bar=False).astype("float32")
        if self._index is None:
            self._index = faiss.IndexFlatL2(embeddings.shape[1])
        self._index.add(embeddings)
        self._docs.extend(texts)
        self._save()
        print(f"✅ [{self._label}] added {len(texts)} docs → total {len(self._docs)}")

    def replace_documents(self, texts: list[str]):
        """Replace this store with a freshly embedded document set."""
        self._index = None
        self._docs = []

        if not texts:
            self.clear()
            print(f"✅ [{self._label}] cleared; no docs to store")
            return

        model = _get_model()
        embeddings = model.encode(texts, show_progress_bar=False).astype("float32")
        self._index = faiss.IndexFlatL2(embeddings.shape[1])
        self._index.add(embeddings)
        self._docs = list(texts)
        self._save()
        print(f"✅ [{self._label}] rebuilt with {len(self._docs)} docs")

    def clear(self):
        self._index = None
        self._docs = []
        for path in (self._index_path, self._docs_path):
            if os.path.exists(path):
                os.remove(path)

    # ── read ──────────────────────────────────────────────────────

    def search(self, query: str, k: int = TOP_K) -> list[tuple[str, float]]:
        """Returns [(doc_text, l2_distance), ...] sorted by distance ascending."""
        if self._index is None or not self._docs:
            return []
        model = _get_model()
        q_vec = model.encode([query]).astype("float32")
        actual_k = min(k, len(self._docs))
        distances, indices = self._index.search(q_vec, actual_k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if 0 <= idx < len(self._docs):
                results.append((self._docs[idx], float(dist)))
        return results

    @property
    def is_ready(self) -> bool:
        return self._index is not None and len(self._docs) > 0

    @property
    def doc_count(self) -> int:
        return len(self._docs)
