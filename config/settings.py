"""
YoWhats Agent — Central Configuration
Load secrets from .env; all other values are tunable constants here.
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────────
# MongoDB
# ─────────────────────────────────────────────
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://techvaseegrah:gowhats%24tech2k25@gowhats.toqv1xm.mongodb.net/gowhats?retryWrites=true&w=majority&appName=Gowhats"
)
MONGO_DB_NAME = "gowhats"
MONGO_CONV_COLLECTION       = "conversations"
MONGO_SESSION_COLLECTION    = "sessions"
MONGO_CHECKPOINT_COLLECTION = "checkpoints"
MONGO_VECTOR_COLLECTION     = "rag_vectors"

# ─────────────────────────────────────────────
# Anthropic / Claude
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-3-haiku-20240307"
CLAUDE_MAX_TOKENS = 800          # raised for complete product-list answers

# ─────────────────────────────────────────────
# Vector Store (FAISS) — paths
# ─────────────────────────────────────────────
EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K       = 6          # retrieve more chunks so product lists are complete

# Default (shared) company knowledge base — always loaded for every user
DEFAULT_RAG_DIR   = "data/default"
DEFAULT_INDEX     = "data/default/index.bin"
DEFAULT_DOCS      = "data/default/docs.pkl"

# Per-customer RAG base path — data/customers/<api_key>/
CUSTOMER_RAG_BASE = "data/customers"

# ─────────────────────────────────────────────
# Web Search — Tavily AI
# ─────────────────────────────────────────────
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY", "")
TAVILY_MAX_RESULTS = 5

# ─────────────────────────────────────────────
# Agent behaviour — RAG confidence bands (L2 distance)
# ─────────────────────────────────────────────
# all-MiniLM-L6-v2 typical distances: 0.3–1.2 = good, 1.5–2.5 = fair, >2.5 = poor
RAG_DISTANCE_GOOD   = 1.5    # ≤ 1.5 → high confidence, skip web
RAG_DISTANCE_FAIR   = 2.5    # ≤ 2.5 → use RAG + also run web for enrichment
                              # > 2.5 → RAG weak, rely on web

MAX_RETRIES = 3

# Domain keywords — any match = allow query through domain guard
DOMAIN_KEYWORDS = [
    # products
    "hair", "skin", "face", "oil", "mask", "powder", "pack", "shampoo",
    "herbal", "organic", "natural", "ayurvedic", "bath", "cleanser",
    "henna", "indigo", "hibiscus", "moringa", "amla", "castor",
    "coconut", "groundnut", "almond", "flaxseed", "eyebrow",
    "tooth", "mouth", "tea", "soup", "hydrosol", "kajal", "loofah",
    # commerce
    "buy", "purchase", "price", "cost", "rate", "stock", "available",
    "discount", "offer", "return", "refund", "shipping", "track",
    "delivery", "order", "invoice", "payment", "cod", "wallet",
    "product", "ingredients", "how to use", "apply", "benefits",
    "booking", "book", "catalog", "more products", "list", "show me",
    # company
    "vaseegrah", "veda", "yowhats", "gowhats", "founder", "store",
    "company", "location", "address", "hours", "contact", "website",
    "register", "msme", "license",
    # general intent words — short queries often use only these
    "what", "which", "how", "where", "when", "tell me", "give me",
    "show", "list", "help", "more", "other", "another",
]