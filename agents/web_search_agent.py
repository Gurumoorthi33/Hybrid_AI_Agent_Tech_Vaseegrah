"""
agents/web_search_agent.py
Web Search Agent Team — powered by Tavily AI Search API.

Tavily returns pre-extracted, clean content per result (no scraping needed),
which makes the pipeline faster and more reliable than raw HTML scraping.

Pipeline:
  Search Sub-Agent   → Tavily API (returns title + url + content)
  Summarizer Agent   → Claude Haiku condenses each result to the query
  Validator Agent    → Keyword overlap confidence scoring
  Orchestrator       → Combines, ranks, returns final docs + sources

.env variable required:
  TAVILY_API_KEY=tvly-dev-...
"""

import os
from tavily import TavilyClient
from config.settings import MAX_RETRIES, CLAUDE_MODEL

# ─────────────────────── Tavily client (lazy init) ──────────────

def _get_tavily() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "TAVILY_API_KEY not set. Add it to your .env file:\n"
            "  TAVILY_API_KEY=tvly-dev-..."
        )
    return TavilyClient(api_key=api_key)


# ─────────────────────── Search Sub-Agent ───────────────────────

def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Calls Tavily and returns list of:
      { "title": str, "url": str, "content": str, "score": float }

    Tavily already returns clean extracted content — no scraping needed.
    """
    try:
        tavily = _get_tavily()
        response = tavily.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",     # deep extraction
            include_answer=False,        # we do our own summarization
            include_raw_content=False,   # clean content is enough
        )
        results = []
        for r in response.get("results", []):
            results.append({
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "content": r.get("content", ""),   # Tavily pre-extracts this
                "score":   r.get("score", 0.0),    # Tavily relevance score
            })
        return results
    except Exception as e:
        print(f"⚠️  Tavily search failed: {e}")
        return []


# ─────────────────────── Summarizer Sub-Agent ───────────────────

def summarize_result(query: str, content: str, client) -> str:
    """
    Uses Claude Haiku to condense a Tavily result to what's
    relevant for the user's query (3-5 sentences max).
    """
    if not content.strip():
        return ""
    try:
        prompt = (
            f"You are a summarizer for a VaseegrahVeda e-commerce assistant.\n"
            f"From the content below, extract ONLY what is relevant to: '{query}'\n"
            f"Be concise — 2 to 4 sentences maximum. Skip irrelevant info.\n\n"
            f"Content:\n{content[:2500]}"
        )
        res = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.content[0].text.strip()
    except Exception as e:
        print(f"⚠️  Summarizer failed: {e}")
        return content[:400]


# ─────────────────────── Validator Sub-Agent ────────────────────

def validate_result(query: str, summary: str, tavily_score: float) -> tuple[bool, float]:
    """
    Combines Tavily's own relevance score with keyword overlap.
    Returns (is_relevant: bool, confidence: float 0-1).
    """
    if not summary:
        return False, 0.0

    q_words = set(query.lower().split())
    s_words = set(summary.lower().split())
    overlap = len(q_words & s_words)
    keyword_conf = min(1.0, overlap / max(len(q_words), 1) * 2)

    # Blend: 60% Tavily score + 40% keyword overlap
    blended = round((tavily_score * 0.6) + (keyword_conf * 0.4), 3)
    return blended > 0.1, blended


# ─────────────────────── Orchestrator ───────────────────────────

def web_search_team(query: str, client) -> dict:
    """
    Full Tavily-powered web search pipeline:
      1. Tavily Search  → clean results with relevance scores
      2. Summarizer     → Claude condenses each result
      3. Validator      → blended confidence scoring
      4. Return         → top docs, sources, avg confidence

    Returns:
        {
            "docs":       [str, ...],
            "sources":    [url, ...],
            "confidence": float,
        }
    """
    search_results = search_web(query, max_results=5)
    if not search_results:
        return {"docs": [], "sources": [], "confidence": 0.0}

    summaries  = []
    sources    = []
    confidences = []

    for result in search_results[:3]:   # process top 3
        content      = result["content"]
        url          = result["url"]
        tavily_score = result["score"]

        summary = summarize_result(query, content, client)
        is_valid, conf = validate_result(query, summary, tavily_score)

        if is_valid and summary:
            summaries.append(summary)
            sources.append(url)
            confidences.append(conf)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "docs":       summaries,
        "sources":    sources,
        "confidence": round(avg_conf, 3),
    }