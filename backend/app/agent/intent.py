"""Lightweight keyword interpretation used for (a) candidate retrieval before the model is called and
(b) the clearly-labelled offline fallback. It is intentionally simple and transparent."""
from __future__ import annotations

import re
from typing import Optional

DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "performance": ["fps", "frame rate", "framerate", "frames", "frame drop", "stutter", "choppy", "smooth", "smoother",
                    "performance", "lag spike", "low-end", "laptop", "drops", "dips", "runs badly", "slow pc"],
    "input_latency": ["input lag", "input delay", "latency", "delay", "responsive", "responsiveness", "low lag",
                      "reaction", "competitive edge"],
    "visibility": ["see enemies", "see players", "spot enemies", "spot players", "visibility", "visible", "clarity",
                   "clear view", "clearer", "player visibility", "contrast", "hard to see", "seeing enemies"],
    "visual_quality": ["look better", "looks better", "pretty", "beautiful", "eye candy", "visual quality",
                       "graphics quality", "max graphics", "nicer"],
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
SESSION_HINTS = [r"\btoday\b", r"\bthis session\b", r"\bfor now\b", r"\bjust this\b", r"\btonight\b"]
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


def mentioned_setting_terms(text: str) -> Optional[str]:
    """Extract the noun phrase after 'what does'/'where is' style questions, for catalogue search."""
    t = (text or "").lower()
    m = re.search(r"(what (does|do|is|are)|where (is|are)|explain|find|show me( where)?)( the)? ([a-z0-9 /\-+]+?)( do| setting| option)?[?.!]?$", t)
    return m.group(6).strip() if m else None
