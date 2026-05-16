"""
Multilingual conversation profiling.

This is intentionally lightweight and local: it detects scripts, common
language markers, and code-mixed style so the generator can mirror the user's
preferred language pattern without adding another LLM call.
"""

import re
from collections import Counter


LANG_MARKERS: dict[str, set[str]] = {
    "english": {
        "the", "is", "are", "what", "how", "where", "when", "please", "need",
        "want", "price", "order", "delivery", "product", "help",
        "hair", "oil", "skin", "face", "use", "buy", "shipping", "payment",
        "website", "api", "status", "stock", "available",
    },
    "tamil": {
        "enna", "epdi", "eppadi", "iruku", "irukka", "venum", "vendum",
        "sollunga", "solunga", "unga", "naan", "nalla", "evlo", "sapadu",
        "marundhu", "mudi", "thala", "oil", "use", "pannalam",
    },
    "french": {
        "bonjour", "merci", "svp", "s'il", "vous", "comment", "combien",
        "produit", "commande", "livraison", "prix", "acheter", "je", "est",
    },
    "spanish": {
        "hola", "gracias", "por", "favor", "como", "cuanto", "producto",
        "pedido", "envio", "precio", "comprar", "quiero", "necesito",
    },
    "japanese": {
        "konnichiwa", "arigato", "ikura", "kudasai", "desu", "masu",
        "shohin", "chumon", "haitatsu",
    },
}

SCRIPT_RANGES: tuple[tuple[str, str, str], ...] = (
    ("tamil", "\u0b80", "\u0bff"),
    ("japanese", "\u3040", "\u30ff"),
    ("japanese", "\u4e00", "\u9fff"),
    ("korean", "\uac00", "\ud7af"),
    ("arabic", "\u0600", "\u06ff"),
    ("devanagari", "\u0900", "\u097f"),
    ("cyrillic", "\u0400", "\u04ff"),
)


def _script_for_char(ch: str) -> str | None:
    for name, start, end in SCRIPT_RANGES:
        if start <= ch <= end:
            return name
    if "a" <= ch.lower() <= "z":
        return "latin"
    return None


def detect_language_profile(text: str, history: list[dict] | None = None) -> dict:
    sample = " ".join(
        [turn.get("content", "") for turn in (history or [])[-4:] if turn.get("role") == "user"]
        + [text]
    )
    words = re.findall(r"[\w']+", sample.lower(), flags=re.UNICODE)
    marker_scores = Counter()
    for word in words:
        for lang, markers in LANG_MARKERS.items():
            if word in markers:
                marker_scores[lang] += 1

    script_counts = Counter()
    for ch in sample:
        script = _script_for_char(ch)
        if script:
            script_counts[script] += 1

    detected = []
    for script, count in script_counts.items():
        if script != "latin" and count >= 2:
            detected.append(script)
    for lang, score in marker_scores.most_common():
        if score > 0 and lang not in detected:
            detected.append(lang)

    if script_counts.get("latin", 0) > 0 and "english" not in detected:
        if marker_scores.get("english", 0) > 0 or not detected:
            detected.insert(0, "english")

    primary = detected[0] if detected else "english"
    secondary = [lang for lang in detected[1:] if lang != primary]
    is_mixed = len(detected) > 1

    if is_mixed:
        response_mode = (
            "Mirror the user's code-mixed style. Keep the same language blend "
            "and use English for technical/API terms."
        )
    elif primary == "english":
        response_mode = "Respond in natural English."
    else:
        response_mode = (
            f"Respond primarily in {primary}. Keep product names, API terms, "
            "URLs, and exact business terms unchanged."
        )

    return {
        "primary_language": primary,
        "secondary_languages": secondary,
        "detected_languages": detected or ["english"],
        "is_mixed_language": is_mixed,
        "script_counts": dict(script_counts),
        "response_mode": response_mode,
    }


def profile_summary(profile: dict) -> str:
    langs = ", ".join(profile.get("detected_languages") or ["english"])
    mixed = "mixed" if profile.get("is_mixed_language") else "single"
    return f"{mixed}; languages={langs}; mode={profile.get('response_mode', '')}"
