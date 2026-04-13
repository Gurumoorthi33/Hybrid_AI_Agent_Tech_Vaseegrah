"""
agents/generator_agent.py
Final Response Generator — produces the customer-facing answer.

Key improvements:
- Intent-aware prompt shaping (different prompts for product_list vs inquiry)
- Explicit instruction to use ALL retrieved context, not just the first chunk
- Categorised product-list expansion
- Booking / ordering flow guidance
- Never says "I don't have enough information" if context is present
"""

from config.settings import CLAUDE_MODEL, CLAUDE_MAX_TOKENS

# ── System prompt ─────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Chattu — the warm, knowledgeable AI assistant for VaseegrahVeda,
a natural herbal products company from Thanjavur, Tamil Nadu, India.

Core personality:
- Friendly, helpful, professional — like a trusted shop assistant over WhatsApp
- Use "sir" or "ma'am" occasionally to be polite
- Respond in clear, conversational language (not bullet walls)
- Be COMPLETE — never cut a product list short, never say "and more" if you know the items

Hard rules:
- Do NOT invent prices — say "please check www.vaseegrahveda.com for the latest price"
- Do NOT confirm real-time stock — say "type the product name followed by * to check stock"
- Do NOT give medical advice — stick to product usage guidance from the knowledge base
- ALWAYS use the context provided — if context has the answer, use it fully
- NEVER say "I don't have enough information" if the context block is non-empty"""


# ── Intent-specific prompt injections ────────────────────────────
INTENT_GUIDANCE = {
    "product_list": (
        "The customer wants to see a PRODUCT LIST.\n"
        "Instructions:\n"
        "1. List ALL products mentioned in the context — do not truncate.\n"
        "2. Group by category: Oils | Hair Masks & Packs | Face Packs | "
        "Powders | Tooth & Oral Care | Teas & Soups | Accessories & Others.\n"
        "3. If a category has no items in the context, omit it.\n"
        "4. After the list, invite them to ask about any specific product.\n"
        "Format: use category headers and short bullet points."
    ),
    "product_inquiry": (
        "The customer is asking about a SPECIFIC PRODUCT.\n"
        "Instructions:\n"
        "1. Answer directly using the context — name, benefits, how to use, sizes, shelf life.\n"
        "2. If multiple products match, briefly cover each.\n"
        "3. End with: 'For price/stock, visit www.vaseegrahveda.com or type the product name followed by *'"
    ),
    "booking_inquiry": (
        "The customer wants to PLACE AN ORDER or BOOK a product.\n"
        "Instructions:\n"
        "1. Explain the two ways to order: Website (www.vaseegrahveda.com for India, "
        "www.vaseegrahveda.sg for Singapore) and WhatsApp catalog (https://wa.me/c/918248860985).\n"
        "2. Mention they don't need an account — guest checkout works.\n"
        "3. Mention order confirmation comes via WhatsApp/email.\n"
        "Keep it short and action-oriented."
    ),
    "order_management": (
        "The customer is asking about an EXISTING ORDER.\n"
        "Provide exact instructions from the context about tracking, cancellation, or modification.\n"
        "If they haven't shared an order ID, ask for it politely."
    ),
    "shipping_delivery": (
        "Answer the SHIPPING / DELIVERY question using context details.\n"
        "Include: dispatch time, delivery days, couriers used, free shipping threshold, "
        "international availability."
    ),
    "payment_billing": (
        "Answer the PAYMENT / REFUND question using context details.\n"
        "Cover: accepted methods, COD status, refund timeline, what to do if payment fails."
    ),
    "company_info": (
        "Answer the COMPANY INFO question using context details.\n"
        "Be factual and complete — founder, location, hours, registrations, contact details."
    ),
}


# ── Context builder ───────────────────────────────────────────────
def _build_context(rag_docs: list[str], web_docs: list[str]) -> str:
    parts = []
    if rag_docs:
        parts.append("── Internal Knowledge Base ──\n" + "\n\n".join(rag_docs))
    if web_docs:
        parts.append("── Web Search Results ──\n" + "\n\n".join(web_docs))
    return "\n\n".join(parts) if parts else ""


# ── Main generator ────────────────────────────────────────────────
def generate_response(
    query: str,
    rag_result: dict,
    web_result: dict,
    history: list[dict],
    intent: str,
    client,
) -> str:
    context = _build_context(
        rag_result.get("docs", []),
        web_result.get("docs", []),
    )

    intent_guide = INTENT_GUIDANCE.get(
        intent,
        "Answer the customer's question completely and helpfully using the context."
    )

    # Build messages: history + current turn
    messages = []
    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    if context:
        user_content = (
            f"[Customer Intent: {intent}]\n\n"
            f"[Response Instructions]\n{intent_guide}\n\n"
            f"[Retrieved Context — use this fully]\n{context}\n\n"
            f"[Customer Message]\n{query}"
        )
    else:
        # No context at all — use general knowledge + be transparent
        user_content = (
            f"[Customer Intent: {intent}]\n\n"
            f"[Response Instructions]\n{intent_guide}\n\n"
            f"[Note: No context was retrieved. Answer from your general knowledge "
            f"about VaseegrahVeda. If truly unknown, guide them to the website or "
            f"customer support.]\n\n"
            f"[Customer Message]\n{query}"
        )

    messages.append({"role": "user", "content": user_content})

    try:
        res = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return res.content[0].text.strip()
    except Exception as e:
        print(f"⚠️  Generator error: {e}")
        return (
            "Sorry sir/ma'am, I'm having a technical issue right now. "
            "Please try again or reach us at +91 9786424450 on WhatsApp."
        )