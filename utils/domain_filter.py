"""
utils/domain_filter.py
Lightweight domain guard.
Philosophy: be PERMISSIVE — let the LLM handle edge cases gracefully.
Only hard-block clearly off-topic and harmful topics.
"""

from config.settings import DOMAIN_KEYWORDS

# Absolute hard blocks — never answer these
HARD_BLOCKED = [
    "politics", "election", "vote", "government policy",
    "war", "military", "weapon",
    "cryptocurrency", "bitcoin", "stock tip", "investment advice",
    "legal advice", "court", "lawsuit",
    "medical diagnosis", "prescription drug", "dosage",
    "self-harm", "suicide",
    "adult content", "pornography",
]


def is_in_domain(query: str) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    Very short queries (≤ 5 words) always pass — they're usually
    product names or single-word intents like "help" / "hi".
    """
    q = query.lower().strip()

    # Hard blocks first
    for blocked in HARD_BLOCKED:
        if blocked in q:
            return False, (
                "I'm Chattu, VaseegrahVeda's shopping assistant. "
                "I can help with our herbal products, orders, and company info. "
                "What can I help you with today?"
            )

    # Short queries always pass
    if len(query.split()) <= 5:
        return True, ""

    # Any domain keyword present → allow
    for kw in DOMAIN_KEYWORDS:
        if kw in q:
            return True, ""

    # Long query with zero domain keywords → redirect politely
    return False, (
        "I'm Chattu, your VaseegrahVeda assistant! 🌿 "
        "I can help with our herbal product range, orders, shipping, "
        "payments, and company information. "
        "What would you like to know?"
    )