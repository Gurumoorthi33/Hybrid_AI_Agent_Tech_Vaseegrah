"""
agents/intent_classifier.py
Two-stage intent classifier:
  Stage 1 — fast keyword scoring  (no API call)
  Stage 2 — LLM classification   (only when stage 1 score == 0)

Intent labels and what they trigger:
  product_inquiry      → RAG retrieval focused on product KB
  product_list         → RAG retrieval + expand/categorize product list
  order_management     → RAG retrieval focused on order/tracking info
  shipping_delivery    → RAG retrieval focused on shipping info
  payment_billing      → RAG retrieval focused on payment/refund info
  company_info         → RAG retrieval focused on company/about info
  booking_inquiry      → RAG + explain ordering flow
  general_ecommerce    → RAG broad retrieval
"""

from config.settings import OPENAI_MODEL

# ─────────────────────── Intent keyword map ──────────────────────
# Each intent has a primary list (higher weight) and a secondary list
INTENT_KEYWORDS: dict[str, dict] = {
    "product_list": {
        "primary": [
            "list", "show all", "show me", "all products", "more products",
            "what products", "what do you sell", "what oils", "what packs",
            "other products", "another product", "more options", "catalog",
            "full list", "all items", "range of", "varieties",
        ],
        "secondary": ["product", "available", "have", "offer", "sell"],
    },
    "product_inquiry": {
        "primary": [
            "hair growth", "herbal black", "dandruff", "citrullus", "moringa",
            "almond", "flaxseed", "castor", "coconut", "groundnut", "eyebrow",
            "face pack", "hair mask", "curly", "henna", "indigo", "hibiscus",
            "avarampoo", "papaya", "banana", "orange", "cocoa", "floral",
            "anti acne", "tooth powder", "mouth freshener", "hydrosol",
            "kajal", "deep conditioning", "baby bath", "rose petal",
            "how to use", "how do i use", "apply", "benefits of",
            "ingredients", "shelf life", "size", "available in", "price of",
            "rate of", "cost of", "what is", "tell me about",
        ],
        "secondary": [
            "oil", "mask", "powder", "pack", "cleanser", "shampoo",
            "skin", "hair", "face", "scalp", "product",
        ],
    },
    "booking_inquiry": {
        "primary": [
            "book", "booking", "place order", "how to order", "how to buy",
            "purchase", "buy", "add to cart", "checkout", "where to order",
            "can i order", "ordering process", "how do i get",
        ],
        "secondary": ["order", "buy", "get", "purchase"],
    },
    "order_management": {
        "primary": [
            "track", "tracking", "order status", "where is my order",
            "cancel order", "modify order", "order id", "dispatch",
            "shipped", "invoice", "confirmation",
        ],
        "secondary": ["order", "status", "delivery", "cancel"],
    },
    "shipping_delivery": {
        "primary": [
            "shipping", "delivery time", "how long", "days to deliver",
            "free shipping", "express", "standard shipping", "courier",
            "international", "singapore", "india post", "delhivery",
        ],
        "secondary": ["ship", "deliver", "days", "time"],
    },
    "payment_billing": {
        "primary": [
            "payment", "refund", "return policy", "cod", "cash on delivery",
            "upi", "gpay", "paytm", "credit card", "debit card",
            "how to pay", "payment failed", "money back",
        ],
        "secondary": ["pay", "money", "refund", "return"],
    },
    "company_info": {
        "primary": [
            "founder", "who started", "who is the owner", "about vaseegrah",
            "company info", "address", "location", "working hours",
            "business hours", "msme", "license", "press", "csr",
            "contact", "phone number", "whatsapp number", "website",
        ],
        "secondary": ["company", "vaseegrah", "store", "office"],
    },
    "general_ecommerce": {
        "primary": [
            "help", "what can you do", "hello", "hi", "hey",
            "account", "login", "signup", "password reset",
        ],
        "secondary": ["assist", "support", "customer service"],
    },
}


def classify_intent(query: str) -> tuple[str, int]:
    """
    Returns (intent_label, confidence_score).
    confidence_score = total keyword hits (0 = no match found).
    """
    q = query.lower().strip()
    best_intent = "general_ecommerce"
    best_score  = 0

    for intent, kw_sets in INTENT_KEYWORDS.items():
        score = 0
        for kw in kw_sets["primary"]:
            if kw in q:
                score += 2          # primary keywords worth 2
        for kw in kw_sets["secondary"]:
            if kw in q:
                score += 1          # secondary worth 1
        if score > best_score:
            best_score  = score
            best_intent = intent

    return best_intent, best_score


def llm_classify(query: str, client) -> str:
    """
    LLM fallback — called only when keyword score == 0.
    Returns one of the intent labels above.
    """
    labels = " | ".join(INTENT_KEYWORDS.keys())
    prompt = (
        f"You are a multilingual intent classifier for a herbal e-commerce chatbot (VaseegrahVeda).\n"
        f"Classify this customer message into exactly ONE of these intents:\n"
        f"{labels}\n\n"
        f"Customer message: \"{query}\"\n\n"
        f"Rules:\n"
        f"- The customer may mix languages, including Tamil+English, French+English, Spanish+English, Japanese+English, or other combinations.\n"
        f"- Understand the meaning before choosing the label.\n"
        f"- If asking about a specific product → product_inquiry\n"
        f"- If asking to list/show products → product_list\n"
        f"- If asking how to order/buy → booking_inquiry\n"
        f"- Reply with ONLY the intent label, nothing else."
    )
    try:
        res = client.messages.create(
            model=OPENAI_MODEL,
            max_tokens=15,
            messages=[{"role": "user", "content": prompt}]
        )
        label = res.content[0].text.strip().lower().replace(" ", "_")
        return label if label in INTENT_KEYWORDS else "general_ecommerce"
    except Exception:
        return "general_ecommerce"
