"""
graph/agent_graph.py
LangGraph orchestration — ReAct-style pipeline with 3-band RAG routing.

Pipeline:
  User Query
    → [domain_guard]         — hard-block off-topic queries
    → [load_memory]          — inject MongoDB conversation history
    → [intent_classifier]    — classify intent (keyword + LLM fallback)
    → [rag_retriever]        — search default KB + customer KB (if any)
    → [rag_router]           ─── 3-way routing on RAG confidence band:
         │ "high"   ──────────────────────────────────► [generator]
         │ "fair"   ──► [web_search] ──► [merge] ──────► [generator]
         └ "low"    ──► [web_search] ──────────────────► [generator]
    → [save_memory]          — persist turn + ReAct trace to MongoDB
    → END

Confidence bands (set in config/settings.py):
  high  L2 dist ≤ 1.5   RAG is sufficient
  fair  L2 dist ≤ 2.5   RAG + web enrichment
  low   L2 dist > 2.5   web search only

Multi-tenant: api_key is threaded through state so retriever_agent
searches both the shared default KB and the customer's private KB.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from anthropic import Anthropic

from agents.intent_classifier import classify_intent, llm_classify
from agents.retriever_agent   import retrieve
from agents.web_search_agent  import web_search_team
from agents.generator_agent   import generate_response
from utils.domain_filter      import is_in_domain
from memory.mongo_memory      import MongoMemory
from config.settings          import ANTHROPIC_API_KEY


# ── State schema ──────────────────────────────────────────────────

class AgentState(TypedDict):
    # ── inputs ──────────────────────────────
    query:      str
    user_id:    str
    session_id: str
    api_key:    Optional[str]   # customer API key (None = no private RAG)

    # ── intermediate ────────────────────────
    intent:      str
    rag_result:  dict
    web_result:  dict
    rag_band:    str            # "high" | "fair" | "low"
    history:     list[dict]

    # ── ReAct trace ─────────────────────────
    thoughts:    list[str]

    # ── outputs ─────────────────────────────
    answer:       str
    blocked:      bool
    block_reason: str


# ── Singletons ────────────────────────────────────────────────────

_client = Anthropic(api_key=ANTHROPIC_API_KEY)
_memory = MongoMemory()

_EMPTY_RAG = {"docs": [], "sources": [], "distances": [], "confidence": "low", "best_dist": 9999.0}
_EMPTY_WEB = {"docs": [], "sources": [], "confidence": 0.0}


# ── Node: Domain Guard ────────────────────────────────────────────

def domain_guard_node(state: AgentState) -> AgentState:
    allowed, reason = is_in_domain(state["query"])
    state["thoughts"].append(f"[DomainGuard] allowed={allowed}")
    if not allowed:
        state["blocked"]      = True
        state["block_reason"] = reason
        state["answer"]       = reason
    return state


# ── Node: Load Memory ─────────────────────────────────────────────

def load_memory_node(state: AgentState) -> AgentState:
    history = _memory.get_history(state["user_id"], state["session_id"], limit=8)
    state["history"] = history
    state["thoughts"].append(f"[Memory] {len(history)} turns loaded")
    return state


# ── Node: Intent Classifier ───────────────────────────────────────

def intent_node(state: AgentState) -> AgentState:
    intent, score = classify_intent(state["query"])
    if score == 0:
        # Zero keyword hits → use LLM
        intent = llm_classify(state["query"], _client)
        state["thoughts"].append(f"[Intent] LLM classified → {intent}")
    else:
        state["thoughts"].append(f"[Intent] keyword classified → {intent} (score={score})")
    state["intent"] = intent
    return state


# ── Node: RAG Retriever ───────────────────────────────────────────

def rag_node(state: AgentState) -> AgentState:
    result = retrieve(
        query   = state["query"],
        api_key = state.get("api_key"),
    )
    state["rag_result"] = result
    state["rag_band"]   = result["confidence"]   # "high" | "fair" | "low"
    state["thoughts"].append(
        f"[RAG] band={result['confidence']} "
        f"best_dist={result['best_dist']:.3f} "
        f"docs={len(result['docs'])}"
    )
    _memory.save_checkpoint(state["user_id"], state["session_id"], {
        "action":     "rag_retrieve",
        "input":      state["query"],
        "intent":     state["intent"],
        "band":       result["confidence"],
        "best_dist":  result["best_dist"],
        "doc_count":  len(result["docs"]),
        "sources":    result["sources"],
    })
    return state


# ── Routing function ──────────────────────────────────────────────

def rag_router(state: AgentState) -> str:
    if state.get("blocked"):
        return "end"
    band = state.get("rag_band", "low")
    # "high" → generate straight from RAG (no web call needed)
    # "fair" → RAG + web enrichment
    # "low"  → web search only
    if band == "high":
        return "generate"
    return "web_search"     # handles both "fair" and "low"


# ── Node: Web Search ──────────────────────────────────────────────

def web_search_node(state: AgentState) -> AgentState:
    band = state.get("rag_band", "low")
    state["thoughts"].append(
        f"[WebSearch] triggered — RAG band={band}. Running Tavily search."
    )
    result = web_search_team(state["query"], _client)
    state["web_result"] = result
    state["thoughts"].append(
        f"[WebSearch] got {len(result['docs'])} results "
        f"conf={result['confidence']}"
    )
    _memory.save_checkpoint(state["user_id"], state["session_id"], {
        "action":     "web_search",
        "input":      state["query"],
        "doc_count":  len(result["docs"]),
        "confidence": result["confidence"],
        "sources":    result["sources"],
    })
    return state


# ── Node: Generate ────────────────────────────────────────────────

def generate_node(state: AgentState) -> AgentState:
    # For "fair" band: combine RAG + web
    # For "high" band: only RAG (web_result will be empty)
    # For "low" band:  only web (rag_result docs may be weak but still passed)
    rag_result = state.get("rag_result", _EMPTY_RAG)
    web_result = state.get("web_result", _EMPTY_WEB)

    # For "low" band, don't pass noisy RAG docs to the generator
    if state.get("rag_band") == "low":
        rag_result = _EMPTY_RAG

    answer = generate_response(
        query      = state["query"],
        rag_result = rag_result,
        web_result = web_result,
        history    = state.get("history", []),
        intent     = state.get("intent", "general_ecommerce"),
        client     = _client,
    )
    state["answer"] = answer
    state["thoughts"].append(f"[Generate] answer ready ({len(answer)} chars)")
    return state


# ── Node: Save Memory ─────────────────────────────────────────────

def save_memory_node(state: AgentState) -> AgentState:
    if not state.get("blocked"):
        _memory.add_message(state["user_id"], state["session_id"], "user",      state["query"])
        _memory.add_message(state["user_id"], state["session_id"], "assistant", state["answer"])
        _memory.save_checkpoint(state["user_id"], state["session_id"], {
            "action":       "final_answer",
            "input":        state["query"],
            "output":       state["answer"],
            "intent":       state.get("intent", ""),
            "rag_band":     state.get("rag_band", ""),
            "react_trace":  state.get("thoughts", []),
        })
    return state


# ── Build compiled graph ──────────────────────────────────────────

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("domain_guard",  domain_guard_node)
    g.add_node("load_memory",   load_memory_node)
    g.add_node("intent",        intent_node)
    g.add_node("rag",           rag_node)
    g.add_node("web_search",    web_search_node)
    g.add_node("generate",      generate_node)
    g.add_node("save_memory",   save_memory_node)

    g.set_entry_point("domain_guard")

    g.add_edge("domain_guard", "load_memory")
    g.add_edge("load_memory",  "intent")
    g.add_edge("intent",       "rag")

    g.add_conditional_edges(
        "rag",
        rag_router,
        {
            "generate":   "generate",
            "web_search": "web_search",
            "end":        "save_memory",
        }
    )

    g.add_edge("web_search", "generate")
    g.add_edge("generate",   "save_memory")
    g.add_edge("save_memory", END)

    return g.compile()