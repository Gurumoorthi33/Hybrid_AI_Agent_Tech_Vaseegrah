"""
agents/retriever_agent.py
Multi-tenant RAG Retriever Agent.

For every query it:
  1. Always searches the DEFAULT shared knowledge base (vaseegrah_veda.txt)
  2. Also searches the CUSTOMER's private KB if one exists for their api_key
  3. Merges results, de-duplicates, re-ranks by L2 distance
  4. Returns docs + a confidence band ("high" / "fair" / "low")

Confidence bands drive routing in the graph:
  high → generate directly from RAG
  fair → use RAG + also run Tavily for enrichment
  low  → skip RAG, rely on Tavily
"""

import os
from memory.vector_store import VectorStore
from config.settings import (
    DEFAULT_INDEX, DEFAULT_DOCS,
    CUSTOMER_RAG_BASE, TOP_K,
    RAG_DISTANCE_GOOD, RAG_DISTANCE_FAIR,
)

# Default KB is loaded once at import time (shared across all users)
_default_vs = VectorStore(DEFAULT_INDEX, DEFAULT_DOCS, label="default")


def _get_customer_vs(api_key: str | None) -> VectorStore | None:
    """Load a customer VectorStore if one has been ingested for this api_key."""
    if not api_key:
        return None
    cust_dir   = os.path.join(CUSTOMER_RAG_BASE, api_key)
    index_path = os.path.join(cust_dir, "index.bin")
    docs_path  = os.path.join(cust_dir, "docs.pkl")
    if os.path.exists(index_path) and os.path.exists(docs_path):
        return VectorStore(index_path, docs_path, label=f"customer:{api_key[:8]}")
    return None


def _band(best_distance: float) -> str:
    if best_distance <= RAG_DISTANCE_GOOD:
        return "high"
    if best_distance <= RAG_DISTANCE_FAIR:
        return "fair"
    return "low"


def retrieve(query: str, api_key: str | None = None, k: int = TOP_K) -> dict:
    """
    Returns:
    {
        "docs":       [str, ...],        # deduplicated, ranked by distance
        "sources":    [str, ...],        # "default" or "customer:<id>"
        "distances":  [float, ...],
        "confidence": "high"|"fair"|"low",
        "best_dist":  float,
    }
    """
    raw: list[tuple[str, float, str]] = []   # (text, distance, source_label)

    # 1. Always query the default KB
    if _default_vs.is_ready:
        for text, dist in _default_vs.search(query, k=k):
            raw.append((text, dist, "default"))

    # 2. Query the customer KB if available
    cust_vs = _get_customer_vs(api_key)
    if cust_vs and cust_vs.is_ready:
        for text, dist in cust_vs.search(query, k=k):
            raw.append((text, dist, f"customer:{api_key[:8]}"))

    if not raw:
        return {
            "docs": [], "sources": [], "distances": [],
            "confidence": "low", "best_dist": 9999.0,
        }

    # 3. Sort by distance (best match first), deduplicate identical texts
    raw.sort(key=lambda x: x[1])
    seen: set[str] = set()
    deduped: list[tuple[str, float, str]] = []
    for text, dist, src in raw:
        key = text[:120]   # compare first 120 chars as dedup key
        if key not in seen:
            seen.add(key)
            deduped.append((text, dist, src))

    # 4. Keep top-k after merging
    top = deduped[:k]

    return {
        "docs":       [t for t, _, _ in top],
        "sources":    [s for _, _, s in top],
        "distances":  [d for _, d, _ in top],
        "confidence": _band(top[0][1]),
        "best_dist":  top[0][1],
    }