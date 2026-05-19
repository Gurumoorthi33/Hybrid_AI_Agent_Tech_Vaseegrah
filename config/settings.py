"""
YoWhats Agent — Central Configuration
All secrets and tunable values. Loaded from .env first, then defaults.
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────────
# MongoDB
# ─────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "agenticchatbot")
MONGO_SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000"))
MONGO_CONNECT_TIMEOUT_MS = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "5000"))
MONGO_SOCKET_TIMEOUT_MS = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "20000"))
MONGO_TLS_ALLOW_INVALID_CERTIFICATES = os.getenv(
    "MONGO_TLS_ALLOW_INVALID_CERTIFICATES",
    "false",
).lower() == "true"
MONGO_CONV_COLLECTION       = "conversations"
MONGO_SESSION_COLLECTION    = "sessions"
MONGO_CHECKPOINT_COLLECTION = "checkpoints"
MONGO_VECTOR_COLLECTION     = "rag_vectors"

# ─────────────────────────────────────────────
# OpenAI
# Model name is read from .env — change it there without touching code.
# ─────────────────────────────────────────────
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL      = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "800"))

# Billing display
# Dashboard cost is estimated from request count because usage_logs currently
# records API calls, not model token usage.
API_CALL_COST_INR = float(os.getenv("API_CALL_COST_INR") or "0")

# ─────────────────────────────────────────────
# Vector Store (FAISS)
# ─────────────────────────────────────────────
EMBED_MODEL       = "all-MiniLM-L6-v2"
TOP_K             = 6

DEFAULT_RAG_DIR   = "data/default"
DEFAULT_INDEX     = "data/default/index.bin"
DEFAULT_DOCS      = "data/default/docs.pkl"
CUSTOMER_RAG_BASE = "data/customers"

# ─────────────────────────────────────────────
# Web Search — Tavily AI
# ─────────────────────────────────────────────
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY", "")
TAVILY_MAX_RESULTS = 5

# ─────────────────────────────────────────────
# Dashboard Security (no custom domain)
# ─────────────────────────────────────────────
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "change-me-set-in-env")

# ─────────────────────────────────────────────
# RAG confidence bands (L2 distance thresholds)
# ─────────────────────────────────────────────
RAG_DISTANCE_GOOD = 1.5
RAG_DISTANCE_FAIR = 2.5
MAX_RETRIES       = 3

# ─────────────────────────────────────────────
# Domain keywords
# ─────────────────────────────────────────────
DOMAIN_KEYWORDS = [
    "hair", "skin", "face", "oil", "mask", "powder", "pack", "shampoo",
    "herbal", "organic", "natural", "ayurvedic", "bath", "cleanser",
    "henna", "indigo", "hibiscus", "moringa", "amla", "castor",
    "coconut", "groundnut", "almond", "flaxseed", "eyebrow",
    "tooth", "mouth", "tea", "soup", "hydrosol", "kajal", "loofah",
    "buy", "purchase", "price", "cost", "rate", "stock", "available",
    "discount", "offer", "return", "refund", "shipping", "track",
    "delivery", "order", "invoice", "payment", "cod", "wallet",
    "product", "ingredients", "how to use", "apply", "benefits",
    "booking", "book", "catalog", "more products", "list", "show me",
    "vaseegrah", "veda", "yowhats", "gowhats", "founder", "store",
    "company", "location", "address", "hours", "contact", "website",
    "register", "msme", "license",
    "what", "which", "how", "where", "when", "tell me", "give me",
    "show", "list", "help", "more", "other", "another",
]
