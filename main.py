"""
main.py — YoWhats Agent entry point.

Modes:
  CLI interactive:   python main.py
  Single query:      python main.py "What is hair growth oil?"
  With customer key: python main.py --api-key <key> "Show all products"
"""

import sys, os
from pathlib import Path
import argparse
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv()   # loads ANTHROPIC_API_KEY + TAVILY_API_KEY from .env

from graph.agent_graph import build_graph
from memory.mongo_memory import MongoMemory

_graph  = build_graph()
_memory = MongoMemory()


def run_query(query: str, user_id: str = "default_user", api_key: str | None = None, website_url: str | None = None) -> dict:
    """
    Run a single query through the full agent pipeline.

    Args:
        query    — the user's message
        user_id  — unique identifier for the user (e.g. WhatsApp number)
        api_key  — customer API key; if provided, their private RAG is also searched

    Returns full state dict: answer, intent, rag_band, thoughts, etc.
    """
    session_id = _memory.get_or_create_session(user_id)

    initial_state = {
        "query":        query,
        "user_id":      user_id,
        "session_id":   session_id,
        "api_key":      api_key,
        "website_url":  website_url,
        # intermediate — initialised empty
        "intent":       "",
        "rag_result":   {"docs": [], "sources": [], "distances": [], "confidence": "low", "best_dist": 9999.0},
        "web_result":   {"docs": [], "sources": [], "confidence": 0.0},
        "rag_band":     "low",
        "history":      [],
        "thoughts":     [],
        # output
        "answer":       "",
        "blocked":      False,
        "block_reason": "",
    }

    return _graph.invoke(initial_state)


def cli():
    parser = argparse.ArgumentParser(description="YoWhats Agent CLI")
    parser.add_argument("query",     nargs="*",  help="Query to ask (single-shot mode)")
    parser.add_argument("--api-key", type=str,   default=None,        help="Customer API key")
    parser.add_argument("--user",    type=str,   default="demo_user", help="User ID")
    args = parser.parse_args()

    api_key = args.api_key
    user_id = args.user

    # Single-shot mode
    if args.query:
        query  = " ".join(args.query)
        result = run_query(query, user_id, api_key)
        print(result["answer"])
        return

    # Interactive mode
    print(f"\n🌿 VaseegrahVeda — Chattu AI Assistant")
    print(f"   User: {user_id}  |  Customer RAG: {'✅ '+api_key[:8]+'...' if api_key else '❌ none'}")
    print(f"   Type 'quit' to exit | 'debug' to toggle trace\n")

    debug = False

    while True:
        try:
            query = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! 🌿")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit"):
            print("Thank you for using VaseegrahVeda. Have a wonderful day! 🌿")
            break
        if query.lower() == "debug":
            debug = not debug
            print(f"[Debug: {'ON' if debug else 'OFF'}]")
            continue

        result = run_query(query, user_id, api_key)

        print(f"\nChattu: {result['answer']}\n")

        if debug:
            print("─── ReAct Trace ───────────────────────────────")
            for t in result.get("thoughts", []):
                print(f"  {t}")
            print(f"  Intent  : {result.get('intent')}")
            print(f"  RAG band: {result.get('rag_band')}")
            print("───────────────────────────────────────────────\n")


if __name__ == "__main__":
    cli()
