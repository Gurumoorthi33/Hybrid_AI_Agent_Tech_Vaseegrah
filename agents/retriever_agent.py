"""
agents/retriever_agent.py
Multi-tenant RAG Retriever Agent.

For every query it:
  1. Searches ONLY the customer's private KB when api_key/client_id is provided
  2. Searches the DEFAULT shared knowledge base only for internal calls without
     a customer namespace
  3. Returns docs + a confidence band ("high" / "fair" / "low")

Confidence bands drive routing in the graph:
  high → generate directly from RAG
  fair → use RAG + also run Tavily for enrichment
  low  → skip RAG, rely on Tavily
"""

import os
from memory.vector_store import VectorStore
from memory.customer_config import customer_dir, validate_customer_id
from config.settings import (
    DEFAULT_INDEX, DEFAULT_DOCS,
    TOP_K,
    RAG_DISTANCE_GOOD, RAG_DISTANCE_FAIR,
)

_default_vs: VectorStore | None = None


def _get_default_vs() -> VectorStore:
    """Load the company/internal VectorStore only for non-client retrieval."""
    global _default_vs
    if _default_vs is None:
        _default_vs = VectorStore(DEFAULT_INDEX, DEFAULT_DOCS, label="default")
    return _default_vs


def _get_customer_vs(api_key: str | None) -> VectorStore | None:
    """Load a customer VectorStore if one has been ingested for this api_key."""
    if not api_key:
        return None
    try:
        client_id = validate_customer_id(api_key)
        cust_dir = customer_dir(client_id)
    except ValueError:
        return None
    index_path = os.path.join(cust_dir, "index.bin")
    docs_path  = os.path.join(cust_dir, "docs.pkl")
    if os.path.exists(index_path) and os.path.exists(docs_path):
        return VectorStore(index_path, docs_path, label=f"customer:{client_id[:8]}")
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

    # Client operations are isolated: if a customer namespace is provided, do
    # not read the company/internal default vector store.
    if api_key:
        cust_vs = _get_customer_vs(api_key)
        if cust_vs and cust_vs.is_ready:
            for text, dist in cust_vs.search(query, k=k):
                raw.append((text, dist, f"customer:{api_key[:8]}"))
    else:
        default_vs = _get_default_vs()
        if default_vs.is_ready:
            for text, dist in default_vs.search(query, k=k):
                raw.append((text, dist, "default"))

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
