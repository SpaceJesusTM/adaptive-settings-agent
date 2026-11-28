"""Lightweight keyword interpretation used for (a) candidate retrieval before the model is called and
(b) the clearly-labelled offline fallback. It is intentionally simple and transparent."""
from __future__ import annotations

import re
from typing import Optional

DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "performance": ["fps", "frame rate", "framerate", "frames", "frame drop", "stutter", "choppy", "smooth", "smoother",
                    "performance", "lag spike", "low-end", "laptop", "drops", "dips", "runs badly", "slow pc"],
    "input_latency": ["input lag", "input delay", "latency", "lower latency", "delay", "responsive", "responsiveness", "low lag",
                      "reaction", "competitive edge"],
    "visibility": ["see enemies", "see players", "spot enemies", "spot players", "visibility", "visible", "clarity",
                   "clear view", "clearer", "player visibility", "contrast", "hard to see", "seeing enemies", "clear enemies", "see opponents"],
    "visual_quality": ["look better", "looks better", "pretty", "beautiful", "eye candy", "visual quality", "visual fidelity", "visually detailed", "polished", "richer lighting",
                       "graphics quality", "max graphics", "look nice", "look great", "nicer"],
    "audio_awareness": ["footstep", "footsteps", "hear", "hearing", "sound direction", "audio cue", "positional audio",
                        "directional", "headphones"],
    "communication": ["voice chat", "mic", "microphone", "comms", "callout", "callouts", "teammates talk", "push to talk"],
    "focus": ["distraction", "distracting", "clutter", "cluttered", "clean hud", "minimal", "focus", "less noise"],
    "comfort": ["comfortable", "hold the key", "toggle", "wrist", "hand hurts", "ergonomic"],
    "network_stability": ["packet loss", "ping", "jitter", "rubber band", "rubberband", "connection", "network",
                          "high ping", "teleporting"],
}

EXPLAIN_PATTERNS = [r"\bwhat (does|do|is|are)\b", r"\bexplain\b", r"\bwhat's\b", r"\bmeaning of\b", r"\bhow does\b",
                    r"\bdownside", r"\btrade-?off", r"\bwhy (those|these|did you|that)\b"]
NAVIGATE_PATTERNS = [r"\bwhere (is|are|can i find|do i find)\b", r"\bfind (the )?setting\b", r"\bshow me (where|the)\b",
                     r"\btake me to\b"]
PREFERENCE_PATTERNS = [r"\bi (prefer|care more about|care about|value|would rather|'d rather|don't care about|do not care about)\b",
                       r"\bmore than\b", r"\bover max", r"\bjust for (today|now|this session)\b", r"\bthis session\b",
                       r"\bfrom now on\b", r"\balways\b.*\bprefer\b"]
RECOMMEND_PATTERNS = [
    r"\bshould i (turn|set|enable|disable|use|keep|change|lower|raise)\b",
    r"\b(configure|optimi[sz]e) everything\b",
    r"\b(just installed|fresh install|new install|all settings|full setup|set me up)\b",
    r"\b(what else|anything else|minor tweaks|more tweaks|more settings|additional changes)\b",
    r"\bwhat should i (change|set|do|adjust)\b",
]
CROSS_GAME_RE = re.compile(
    r"(\bvalorant\b.*\bcs2\b|\bcs2\b.*\bvalorant\b"
    r"|\b(equivalent|carry over|same key|analogous|compare.*with|from valorant|from cs2|based on valorant|based on cs2)\b"
    r"|\b(transfer|convert|match)\b.*\b(sens|sensitivity|key|keys|keybind|crosshair|abilities|grenade)\b"
    r"|\b(valorant|cs2)\s+(sens|sensitivity|push-?to-?talk|mic|ping)\b"
    r"|\babilities\b.*\b(grenade|utility|cs2)\b|\b(grenade|utility)\b.*\b(abilities|valorant)\b)",
    re.I,
)
SENS_VALUE_RE = re.compile(
    r"(?:(?:sens(?:itivity)?\s*(?:is|of|=|:|at)?\s*|my\s+)(\d+(?:\.\d+)?)\b|"
    r"\b(\d+(?:\.\d+)?)\s*(?:valorant|cs2)?\s*sens(?:itivity)?\b)",
    re.I,
)
SPECULATIVE_RE = re.compile(
    r"\b(might try|maybe try|thinking about|considering|not sure yet|what if i|might want|curious about)\b",
    re.I,
)
EXPLICIT_MEMORY_RE = re.compile(
    r"\b(remember(?: that)?|don't forget|do not forget|keep in mind|note that|from now on|"
    r"always\s+(?:priorit|prefer|use|keep))\b",
    re.I,
)
_KEY_BIND_RE = re.compile(
    r"\b(?:use|prefer|bound to|bind|is|=)\s+([A-Z0-9][A-Z0-9_]{0,8})\b|\b(MOUSE[1-5]|CAPS\s*LOCK|CAPSLOCK|LSHIFT|SHIFT|LCTRL|CTRL|ALT|SPACE|TAB)\b",
    re.I,
)
SESSION_HINTS = [r"\btoday\b", r"\bthis session\b", r"\bfor now\b", r"\bjust this\b", r"\btonight\b", r"\bonly for (?:today|now)\b"]
DEPRIORITIZE_HINTS = [r"\bdon't care about\b", r"\bdo not care about\b", r"\bless important\b", r"\bnot bothered about\b"]


def detect_dimensions(text: str) -> list[str]:
    t = (text or "").lower()
    found: list[tuple[int, str]] = []
    for dim, words in DIMENSION_KEYWORDS.items():
        positions = [t.find(w) for w in words if w in t]
        if positions:
            found.append((min(positions), dim))
    found.sort()
    return [d for _, d in found]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def classify(text: str) -> str:
    t = (text or "").lower()
    if _any(NAVIGATE_PATTERNS, t):
        return "navigate"
    if _any(RECOMMEND_PATTERNS, t):
        return "recommend"
    if _any(PREFERENCE_PATTERNS, t):
        return "preference"
    if _any(EXPLAIN_PATTERNS, t):
        return "explain"
    if detect_dimensions(t):
        return "recommend"
    return "clarify"


def preference_scope(text: str) -> str:
    return "session" if _any(SESSION_HINTS, (text or "").lower()) else "durable"


def preference_direction_for(text: str, dimension: str) -> str:
    t = (text or "").lower()
    if re.search(r"\bde[- ]?prioriti[sz]e\b|\bput less weight on\b", t) and dimension in detect_dimensions(t):
        return "deprioritize"
    if _any(DEPRIORITIZE_HINTS, t):
        # "I don't care about X" -> X is de-prioritized when X is the dimension mentioned after the phrase.
        m = re.search(r"(don't|do not) care about ([a-z \-]+)", t)
        if m and dimension in detect_dimensions(m.group(2)):
            return "deprioritize"
    m = re.search(r"(more than|over|rather than|instead of) ([a-z \-]+)", t)
    if m and dimension in detect_dimensions(m.group(2)) and dimension not in detect_dimensions(t[: m.start()]):
        return "deprioritize"
    return "prioritize"


def first_sentence(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def is_cross_game_query(text: str) -> bool:
    return bool(CROSS_GAME_RE.search(text or ""))


def extract_sensitivity_number(text: str) -> Optional[float]:
    m = SENS_VALUE_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    if not raw:
        return None
    try:
        val = float(raw)
        return val if 0.05 <= val <= 8.0 else None
    except ValueError:
        return None


def is_speculative(text: str) -> bool:
    t = (text or "").lower()
    if EXPLICIT_MEMORY_RE.search(t) and re.search(r"\b(remember|don't forget|from now on)\b", t):
        return False
    return bool(SPECULATIVE_RE.search(t))


def is_goal_statement(text: str, dims: Optional[list[str]] = None) -> bool:
    t = (text or "").lower().strip()
    if not t or is_speculative(t):
        return False
    if _any(NAVIGATE_PATTERNS, t) or re.search(
        r"^\s*(what (does|do|is|are)|how does|explain|meaning of|why (those|these|did you|that)|what are the downsides)\b",
        t,
    ):
        return False
    if is_cross_game_query(t) and not any(k in t for k in ("set up", "configure", "optimi", "recommend", "suggest", "change")):
        return False
    found_dims = dims if dims is not None else detect_dimensions(t)
    if not found_dims and not _any(RECOMMEND_PATTERNS, t):
        return False
    return bool(
        found_dims
        or _any(RECOMMEND_PATTERNS, t)
        or re.search(r"\b(goal|priorit|optimi[sz]|configure|set up|recommend|suggest|improve|reduce|boost|help)\b", t)
    )


def _extract_key_token(text: str) -> Optional[str]:
    special = re.search(r"\b(MOUSE[1-5]|CAPS\s*LOCK|CAPSLOCK|LSHIFT|RSHIFT|SHIFT|LCTRL|RCTRL|CTRL|ALT|SPACE|TAB)\b", text, re.I)
    if special:
        return re.sub(r"\s+", "", special.group(1).upper())
    stop = {"I", "A", "IN", "TO", "ON", "OR", "IS", "MY", "IT", "AS", "FOR", "THE", "USE", "KEY", "MIC", "PTT", "CS2", "THAT"}
    m = re.search(r"\b(?:use|prefer|bind|bound to|is|=)\s+([A-Za-z0-9])\b", text, re.I)
    if m and m.group(1).upper() not in stop:
        return m.group(1).upper()
    m2 = re.search(r"\b([A-Z])\s+(?:for|as)\s+(?:my\s+)?(?:push[- ]to[- ]talk|ptt|mic|ping)\b", text)
    if m2 and m2.group(1) not in stop:
        return m2.group(1)
    return None


def detect_explicit_memory(text: str, current_game: str) -> list[dict[str, Any]]:
    """Detect unambiguous user memory instructions without over-saving casual, speculative, or Q&A remarks."""
    raw = (text or "").strip()
    lower = raw.lower()
    if not raw or is_speculative(raw):
        return []
    if _any(NAVIGATE_PATTERNS, lower):
        return []
    if re.search(r"^\s*(what|how|why|where|should i|could you convert|convert)\b", lower) and "remember" not in lower:
        return []
    if not EXPLICIT_MEMORY_RE.search(lower):
        return []

    target_game = "valorant" if "valorant" in lower and "cs2" not in lower else (
        "cs2" if "cs2" in lower and "valorant" not in lower else current_game
    )
    out: list[dict[str, Any]] = []

    if any(k in lower for k in ("push-to-talk", "push to talk", "ptt", "mic key", "microphone key", "voice key")):
        tok = _extract_key_token(raw)
        if tok:
            out.append({
                "kind": "fact",
                "factKey": "push_to_talk_key",
                "valueText": tok,
                "scope": "durable",
                "game": target_game,
                "quote": raw[:180],
            })
    if any(k in lower for k in ("ping key", "callout ping", "ping bind")) or ("ping" in lower and "key" in lower):
        tok = _extract_key_token(raw)
        if tok:
            out.append({
                "kind": "fact",
                "factKey": "ping_key",
                "valueText": tok,
                "scope": "durable",
                "game": target_game,
                "quote": raw[:180],
            })
    if any(k in lower for k in ("sensitivity", "sens")) and not any(w in lower for w in ("convert", "equivalent", "what ", "match ")):
        num = extract_sensitivity_number(raw)
        if num is not None:
            out.append({
                "kind": "fact",
                "factKey": "mouse_sensitivity",
                "valueText": str(num),
                "scope": "durable",
                "game": target_game,
                "quote": raw[:180],
            })

    # If the sentence ONLY named a concrete keybind/sensitivity fact, do not also emit a broad dimension weight
    has_priority_phrase = bool(
        re.search(r"\b(priorit|prefer|care more|care about|don't care|do not care|over|rather than|focus on|value)\b", lower)
    )
    dims = detect_dimensions(lower)
    if dims and (not out or (has_priority_phrase and "push" not in lower and "ping" not in lower and "sens" not in lower)):
        scope = preference_scope(lower)
        for d in dims[:2]:
            out.append({
                "kind": "preference",
                "dimension": d,
                "direction": preference_direction_for(lower, d),
                "scope": scope,
                "game": target_game,
                "quote": raw[:180],
            })
    return out


def mentioned_setting_terms(text: str) -> Optional[str]:
    """Extract the noun phrase after 'what does'/'where is' style questions, for catalogue search."""
    t = (text or "").lower()
    m = re.search(
        r"(?:what (?:does|do|is|are)|where (?:is|are)|explain|find|show me(?: where)?|"
        r"should i (?:turn off|turn on|turn|set|enable|disable|use|keep|change|lower|raise))"
        r"(?: the)? ([a-z0-9 /\-+]+?)(?: do| setting| option)?[?.!]?$",
        t,
    )
    return m.group(1).strip() if m else None
