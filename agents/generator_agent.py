"""
agents/generator_agent.py
Final Response Generator
"""

from config.settings import CLAUDE_MODEL, CLAUDE_MAX_TOKENS

SYSTEM_PROMPT = """You are Chattu, a WhatsApp AI assistant for VaseegrahVeda herbal products.

Rules:
- Never use markdown formatting like **bold** or *italic*. Plain text only.
- Maximum 3-4 lines per reply. No exceptions.
- Answer ONLY what was asked. Nothing extra.
- If asked about one product, mention only that product.
- If asked for a list, give max 4-5 items with one-line descriptions only.
- Never list full categories unprompted.
- Use sir or madam once only.
- No prices - say visit www.vaseegrahveda.com
- No stock confirmation - say type product name followed by *
- No medical advice."""

INTENT_GUIDANCE = {
    "product_list": (
        "Give a SHORT list of max 5 products with one-line descriptions. "
        "End with: Type any product name to know more."
    ),
    "product_inquiry": (
        "Answer in 2-3 lines: what it is, key benefit, how to use. "
        "End with: For price visit www.vaseegrahveda.com"
    ),
    "booking_inquiry": (
        "2 lines only: order via www.vaseegrahveda.com or WhatsApp catalog https://wa.me/c/918248860985"
    ),
    "order_management": (
        "Answer directly from context. If no order ID, ask for it in one line."
    ),
    "shipping_delivery": (
        "Answer in 2-3 lines: delivery time and free shipping threshold only."
    ),
    "payment_billing": (
        "Answer the payment question in 2-3 lines from context."
    ),
    "company_info": (
        "Answer in 2-3 lines from context. Be factual."
    ),
}


def _build_context(rag_docs: list, web_docs: list) -> str:
    parts = []
    if rag_docs:
        parts.append("-- Internal Knowledge Base --\n" + "\n\n".join(rag_docs))
    if web_docs:
        parts.append("-- Web Search Results --\n" + "\n\n".join(web_docs))
    return "\n\n".join(parts) if parts else ""


def generate_response(
    query: str,
    rag_result: dict,
    web_result: dict,
    history: list,
    intent: str,
    client,
    system_prompt: str = None,
) -> str:
    context = _build_context(
        rag_result.get("docs", []),
        web_result.get("docs", []),
    )

    active_prompt = system_prompt.strip() if system_prompt else SYSTEM_PROMPT

    intent_guide = INTENT_GUIDANCE.get(
        intent,
        "Answer the customer question in 2-3 lines using the context."
    )

    messages = []
    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    if context:
        user_content = (
            f"[Intent: {intent}]\n"
            f"[Instructions] {intent_guide}\n\n"
            f"[Context]\n{context}\n\n"
            f"[Customer] {query}"
        )
    else:
        user_content = (
            f"[Intent: {intent}]\n"
            f"[Instructions] {intent_guide}\n\n"
            f"[Customer] {query}"
        )

    messages.append({"role": "user", "content": user_content})

    try:
        res = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=active_prompt,
            messages=messages,
        )
        return res.content[0].text.strip()
    except Exception as e:
        print(f"Generator error: {e}")
        return (
            "Sorry sir/madam, I am having a technical issue right now. "
            "Please try again or reach us at +91 9786424450 on WhatsApp."
        )
