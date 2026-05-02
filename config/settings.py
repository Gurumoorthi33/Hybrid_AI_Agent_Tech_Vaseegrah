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
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://techvaseegrah:gowhats%24tech2k25@gowhats.toqv1xm.mongodb.net/gowhats?retryWrites=true&w=majority&appName=Gowhats"
)
MONGO_DB_NAME               = "gowhats"
MONGO_CONV_COLLECTION       = "conversations"
MONGO_SESSION_COLLECTION    = "sessions"
MONGO_CHECKPOINT_COLLECTION = "checkpoints"
MONGO_VECTOR_COLLECTION     = "rag_vectors"

# ─────────────────────────────────────────────
# Anthropic / Claude
# Model name is read from .env — change it there without touching code.
#
# ACTIVE models (May 2026):
#   claude-haiku-4-5-20251001    ← fastest, cheapest  ✅ DEFAULT
#   claude-sonnet-4-5-20250929   ← balanced
#   claude-sonnet-4-6            ← latest balanced
#   claude-opus-4-6              ← most capable
#
# RETIRED (will 404):
#   claude-3-haiku-20240307      ← retired Feb 2026
#   claude-3-5-haiku-20241022    ← retired Feb 2026
#   claude-3-5-sonnet-20241022   ← retired Jan 2026
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
<<<<<<< HEAD
CLAUDE_MODEL      = "claude-haiku-4-5-20251001"
CLAUDE_MAX_TOKENS = 300          # raised for complete product-list answers
=======
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "800"))
>>>>>>> d1cf4b9 (EC2 local changes)

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
