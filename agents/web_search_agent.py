"""
agents/web_search_agent.py
Web Search Agent — powered by Tavily AI Search API.

ROOT CAUSES FIXED:
  1. Raw user queries like "hi" or "hair oil" sent directly to Tavily → fixed by
     query reformulation that builds a proper web-search query with brand context
  2. include_answer=False → now enabled so Tavily's own AI summary is used first
  3. include_raw_content=False → now enabled so full page text is available
  4. Only top 3 results processed → now all 5 processed
  5. Validator threshold 0.08 too low → raised to 0.15
  6. Summarizer too restrictive → now extracts all useful product/company info
  7. search_depth="advanced" wasted without raw content → now consistent
  8. No fallback when Tavily returns empty → graceful fallback added

Pipeline:
  query_reformulator → Tavily search (answer + results + raw content)
  → extract_best_content → summarize → validate → return
"""

import os
import re
from urllib.parse import urlparse

from config.settings import TAVILY_MAX_RESULTS, OPENAI_MODEL

BRAND_CONTEXT = "VaseegrahVeda herbal products Tamil Nadu India"


# ── Lazy Tavily client ────────────────────────────────────────────

def _get_tavily():
    from tavily import TavilyClient
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise EnvironmentError("TAVILY_API_KEY not set in .env")
    return TavilyClient(api_key=api_key)


# ── 1. Query Reformulator ─────────────────────────────────────────

def _website_search_hint(website_url: str | None) -> str | None:
    domain = _normalize_domain(website_url)
    if not domain:
        return None
    return domain.replace("-", " ").replace(".", " ")


def reformulate_query(user_query: str, intent: str = "", website_url: str | None = None) -> str:
    """
    Converts a raw user query into an effective web search query.

    Examples:
      "hi"                   → "VaseegrahVeda herbal products Tamil Nadu"
      "hair oil"             → "VaseegrahVeda hair growth oil benefits ingredients"
      "what oils do you have"→ "VaseegrahVeda herbal hair oils product list"
      "how to order"         → "VaseegrahVeda order online buy herbal products"
      "shipping"             → "VaseegrahVeda shipping delivery India"
    """
    q = user_query.strip().lower()
    brand_context = _website_search_hint(website_url) or BRAND_CONTEXT

    # Very short / greeting → search for brand overview
    if len(q.split()) <= 2 or q in ("hi", "hello", "hey", "help", "?"):
        return f"{brand_context} products catalog"

    # Remove filler words
    fillers = {"what", "which", "how", "tell", "me", "about", "do", "you",
               "have", "can", "i", "get", "is", "are", "the", "a", "an",
               "your", "give", "show", "list", "please", "want", "need"}
    words = [w for w in q.split() if w not in fillers]
    clean = " ".join(words) if words else q

    # Intent-specific query shaping
    intent_prefixes = {
        "product_list":     f"{brand_context} full product catalog",
        "product_inquiry":  f"{brand_context} {clean} benefits ingredients how to use",
        "order_management": f"{brand_context} order {clean} tracking",
        "shipping_delivery":f"{brand_context} shipping delivery time",
        "payment_billing":  f"{brand_context} payment methods refund policy",
        "company_info":     f"{brand_context} company founder location contact",
        "booking_inquiry":  f"{brand_context} how to buy order online website",
    }

    if intent and intent in intent_prefixes:
        return intent_prefixes[intent]

    # Default: prepend the client/site hint so results are brand-specific.
    if brand_context.lower() not in clean:
        return f"{brand_context} {clean}"

    return clean


# ── 2. Tavily Search ──────────────────────────────────────────────

def _normalize_domain(website_url: str | None) -> str | None:
    if not website_url:
        return None

    parsed = urlparse(website_url if "://" in website_url else f"https://{website_url}")
    host = parsed.netloc or parsed.path
    return host.removeprefix("www.") or None


def search_web(
    query: str,
    max_results: int = TAVILY_MAX_RESULTS,
    website_url: str | None = None,
) -> dict:
    """
    Calls Tavily with full content extraction.
    Returns the complete Tavily response dict including:
      - answer: Tavily's own AI-generated answer (best signal)
      - results: list of {title, url, content, raw_content, score}
    """
    try:
        tavily = _get_tavily()
        params = {
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": True,
            "include_raw_content": True,
            "include_images": False,
        }
        domain = _normalize_domain(website_url)
        if domain:
            params["include_domains"] = [domain]

        return tavily.search(**params)
    except Exception as e:
        print(f"⚠️  Tavily search error: {e}")
        return {}


# ── 3. Content Extractor ──────────────────────────────────────────

def extract_best_content(result: dict) -> str:
    """
    From a single Tavily result, extract the richest available text.
    Priority: raw_content → content → title + url
    """
    raw = (result.get("raw_content") or "").strip()
    snippet = (result.get("content") or "").strip()
    title = (result.get("title") or "").strip()

    # raw_content can be very long — take the most useful portion
    if raw and len(raw) > 200:
        # Clean HTML artifacts
        raw = re.sub(r'<[^>]+>', ' ', raw)
        raw = re.sub(r'\s+', ' ', raw).strip()
        return raw[:4000]     # up to 4000 chars for better extraction

    if snippet and len(snippet) > 50:
        return snippet[:2000]

    return title


# ── 4. Summarizer ─────────────────────────────────────────────────

def summarize_content(
    original_query: str,
    content: str,
    client,
    website_url: str | None = None,
) -> str:
    """
    Extract all useful information relevant to the user's query.
    Less restrictive than before — captures product details, prices,
    ingredients, usage, ordering info, company details.
    """
    if not content or not content.strip():
        return ""

    try:
        brand_context = _website_search_hint(website_url) or BRAND_CONTEXT
        prompt = (
            f"You are a knowledgeable assistant for this client: {brand_context}.\n\n"
            f"User asked: \"{original_query}\"\n\n"
            f"From the web content below, extract ALL information that helps answer this query.\n"
            f"Include: product names, benefits, ingredients, prices, how to use, "
            f"ordering process, company details, contact info — whatever is relevant.\n"
            f"Write 3 to 6 clear sentences. Do not add anything not in the content.\n\n"
            f"Web content:\n{content[:3000]}"
        )
        res = client.messages.create(
            model=OPENAI_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.content[0].text.strip()
    except Exception as e:
        print(f"⚠️  Summarizer failed: {e}")
        # Return raw content snippet as fallback — better than nothing
        return content[:500] if content else ""


# ── 5. Validator ──────────────────────────────────────────────────

def validate(original_query: str, summary: str, tavily_score: float) -> tuple[bool, float]:
    """
    Blended confidence scoring.
    Threshold raised from 0.08 to 0.15 to filter out junk results.
    """
    if not summary or len(summary.strip()) < 30:
        return False, 0.0

    q_words = set(re.sub(r'[^\w\s]', '', original_query.lower()).split())
    s_words = set(re.sub(r'[^\w\s]', '', summary.lower()).split())

    # Remove stop words from overlap check
    stops = {"the", "a", "an", "is", "are", "was", "to", "of", "and", "or",
             "in", "on", "at", "for", "with", "it", "this", "that", "be"}
    q_words -= stops
    s_words -= stops

    overlap = len(q_words & s_words)
    kw_conf = min(1.0, overlap / max(len(q_words), 1) * 1.5)

    # Tavily score is 0–1, already a strong relevance signal
    blended = round(tavily_score * 0.65 + kw_conf * 0.35, 3)

    return blended > 0.15, blended   # threshold: 0.08 → 0.15


# ── 6. Main Orchestrator ──────────────────────────────────────────

def web_search_team(
    query: str,
    client,
    website_url: str | None = None,
    intent: str = "",
) -> dict:
    """
    Full pipeline:
      1. Reformulate query for effective web search
      2. Call Tavily (with AI answer + raw content)
      3. Use Tavily's own answer first if available
      4. Extract + summarize each result
      5. Validate relevance
      6. Return merged docs + sources + confidence

    Returns:
        {
            "docs":       [str, ...],   # summaries, best first
            "sources":    [url, ...],
            "confidence": float,
            "search_query": str,        # the actual query sent to Tavily
        }
    """
    # Step 1 — reformulate
    search_query = reformulate_query(query, intent, website_url=website_url)
    print(f"🔍 Tavily search: '{search_query}'")

    # Step 2 — search
    response = search_web(
        search_query,
        max_results=TAVILY_MAX_RESULTS,
        website_url=website_url,
    )
    if not response:
        return {"docs": [], "sources": [], "confidence": 0.0, "search_query": search_query}

    docs       = []
    sources    = []
    confidences = []

    # Step 3 — use Tavily's own AI answer as the first doc (highest quality)
    tavily_answer = (response.get("answer") or "").strip()
    if tavily_answer and len(tavily_answer) > 40:
        docs.append(tavily_answer)
        sources.append("tavily_ai_answer")
        confidences.append(0.9)    # Tavily's answer is always high confidence
        print(f"  ✅ Tavily AI answer: {tavily_answer[:80]}...")

    # Step 4 — process each result
    results = response.get("results", [])
    for result in results:                # process ALL results, not just top 3
        url          = result.get("url", "")
        tavily_score = float(result.get("score", 0.0))

        content = extract_best_content(result)
        if not content:
            continue

        summary = summarize_content(query, content, client, website_url=website_url)
        if not summary:
            continue

        is_valid, conf = validate(query, summary, tavily_score)

        if is_valid:
            docs.append(summary)
            sources.append(url)
            confidences.append(conf)
            print(f"  ✅ Result [{conf:.2f}]: {url[:60]}")
        else:
            print(f"  ❌ Filtered [{conf:.2f}]: {url[:60]}")

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "docs":         docs,
        "sources":      sources,
        "confidence":   round(avg_conf, 3),
        "search_query": search_query,
    }
