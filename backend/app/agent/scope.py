"""Adaptive recommendation scope classification.

Distinguishes narrow questions ("What does anti-aliasing do?", "Should I turn off VSync?") from
category optimizations ("Help reduce input lag"), broad competitive tuning, and full first-time
game setups ("I just installed CS2; configure everything for competitive FPS and clarity").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

ScopeKind = Literal[
    "explain_only",
    "focused",
    "category_optimization",
    "broad_optimization",
    "full_game_setup",
]

DEFAULT_COMPETITIVE_DIMS = [
    "performance",
    "input_latency",
    "visibility",
    "audio_awareness",
    "focus",
]

_FULL_SETUP_RE = re.compile(
    r"\b(just installed|fresh install|new install|brand new|from scratch|first[- ]time setup|"
    r"configure everything|optimi[sz]e everything|set (up )?everything|all settings|full setup|"
    r"entire (menu|game|settings)|every setting|comprehensive)\b",
    re.I,
)
_SUPPLEMENT_RE = re.compile(
    r"\b(what else|anything else|more tweaks|minor tweaks|other tweaks|remaining settings|"
    r"more settings|show more|additional changes)\b",
    re.I,
)
_BROAD_RE = re.compile(
    r"\b(best competitive|competitive (settings|setup|config|preset)|moving from|switching from|"
    r"similar priorities|broad|set me up|general setup|whole game)\b",
    re.I,
)
_SINGLE_ASK_RE = re.compile(
    r"\bshould i (turn|set|enable|disable|use|keep|change|lower|raise)\b",
    re.I,
)
_OPEN_MULTI_ASK_RE = re.compile(r"\b(what|which)\s+should i\b", re.I)
_FOCUSED_LIMIT_RE = re.compile(
    r"\b(most important|top [1-3]|just (a few|one|two|three|the main|the key)|fewest|quickest|"
    r"minimal changes|only the biggest)\b",
    re.I,
)
_EXPLAIN_ONLY_RE = re.compile(
    r"^\s*(what (does|do|is|are)|how does|explain|meaning of|where (is|are|can i find|do i find)|"
    r"find (the )?setting|show me|take me to|why (those|these|did you|that)|what are the downsides)\b",
    re.I,
)
_ACTION_SEEKING_RE = re.compile(
    r"\b(recommend|suggest|what should i (change|set|do|adjust)|what (can|do) i change|what to change|"
    r"set me up|configure|optimi[sz]e|fix|help (me )?(reduce|improve|hear|see|boost)|change whatever|"
    r"make (the game|it)|should i (turn|set|enable|disable|change|lower|raise)|include minor|what else)\b",
    re.I,
)
_PREF_ONLY_RE = re.compile(
    r"\b(i (prefer|care more about|care about|value|would rather|'d rather|don't care about|do not care about)|"
    r"remember(?: that)?|don't forget|from now on)\b",
    re.I,
)
_SPECULATIVE_RE = re.compile(
    r"\b(might try|maybe try|thinking about|considering|not sure yet|what if i|might want|curious about)\b",
    re.I,
)


@dataclass(frozen=True)
class ScopePlan:
    scope: ScopeKind
    max_recs: int
    auto_stage: bool
    include_minor: bool
    is_supplement: bool
    reason: str
    inferred_dimensions: list[str]
    explicit_override: Optional[str] = None
    single_setting_hint: bool = False

    def to_meta(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "maxRecommendations": self.max_recs,
            "includeMinor": self.include_minor,
            "isSupplement": self.is_supplement,
            "reason": self.reason,
            "inferredDimensions": list(self.inferred_dimensions),
            "explicitOverride": self.explicit_override,
            "singleSettingHint": self.single_setting_hint,
        }


def classify_scope(
    message: str,
    *,
    detected_dims: Optional[list[str]] = None,
    has_saved_prefs: bool = False,
    scope_override: Optional[str] = None,
) -> ScopePlan:
    """Classify how broad a recommendation pass should be from user wording and explicit override."""
    text = (message or "").strip()
    lower = text.lower()
    dims = list(dict.fromkeys(detected_dims or []))

    # Pure explanation / navigation / speculative / preference-only statements NEVER auto-stage, even under UI overrides.
    if _SPECULATIVE_RE.search(lower) and not re.search(r"\b(remember|from now on|always)\b", lower):
        return ScopePlan(
            scope="explain_only",
            max_recs=0,
            auto_stage=False,
            include_minor=False,
            is_supplement=False,
            reason="Tentative or exploratory remark: clarify gently without saving goals or staging settings.",
            inferred_dimensions=[],
            explicit_override=scope_override,
        )

    if _EXPLAIN_ONLY_RE.search(lower) and not _ACTION_SEEKING_RE.search(lower):
        return ScopePlan(
            scope="explain_only",
            max_recs=0,
            auto_stage=False,
            include_minor=False,
            is_supplement=False,
            reason="Explanation or navigation question: no changes should be staged.",
            inferred_dimensions=dims,
            explicit_override=scope_override,
        )

    if _PREF_ONLY_RE.search(lower) and not _ACTION_SEEKING_RE.search(lower) and not _FULL_SETUP_RE.search(lower) and not _BROAD_RE.search(lower):
        return ScopePlan(
            scope="explain_only",
            max_recs=0,
            auto_stage=False,
            include_minor=False,
            is_supplement=False,
            reason="Preference statement: handle preference memory cleanly without staging settings automatically.",
            inferred_dimensions=dims,
            explicit_override=scope_override,
        )

    single_ask = bool(_SINGLE_ASK_RE.search(lower) and not _OPEN_MULTI_ASK_RE.search(lower))

    if scope_override == "focused" and (dims or _ACTION_SEEKING_RE.search(lower) or has_saved_prefs):
        return ScopePlan(
            scope="focused",
            max_recs=1 if single_ask else 3,
            auto_stage=True,
            include_minor=False,
            is_supplement=False,
            reason="Focused scope selected: prioritizing only the highest-impact change(s).",
            inferred_dimensions=dims or ["performance", "input_latency"],
            explicit_override="focused",
            single_setting_hint=single_ask,
        )

    if scope_override == "comprehensive" and (dims or _ACTION_SEEKING_RE.search(lower) or _FULL_SETUP_RE.search(lower) or _BROAD_RE.search(lower) or has_saved_prefs):
        eff_dims = dims or list(DEFAULT_COMPETITIVE_DIMS)
        return ScopePlan(
            scope="full_game_setup",
            max_recs=40,
            auto_stage=True,
            include_minor=True,
            is_supplement=bool(_SUPPLEMENT_RE.search(lower)),
            reason="Comprehensive scope selected: auditing the full applicable catalogue.",
            inferred_dimensions=eff_dims,
            explicit_override="comprehensive",
        )

    if single_ask or _FOCUSED_LIMIT_RE.search(lower):
        return ScopePlan(
            scope="focused",
            max_recs=1 if single_ask else 3,
            auto_stage=True,
            include_minor=False,
            is_supplement=False,
            reason="Focused request: checking only the directly requested or top-priority change(s).",
            inferred_dimensions=dims,
            single_setting_hint=single_ask,
        )

    is_supplement = bool(_SUPPLEMENT_RE.search(lower))
    if _FULL_SETUP_RE.search(lower) or is_supplement:
        eff_dims = list(dict.fromkeys(dims + DEFAULT_COMPETITIVE_DIMS)) if ("competitive" in lower or not dims or is_supplement) else dims
        if "visual_quality" in dims and "visual_quality" not in eff_dims:
            eff_dims.append("visual_quality")
        return ScopePlan(
            scope="full_game_setup",
            max_recs=40,
            auto_stage=True,
            include_minor=True,
            is_supplement=is_supplement,
            reason=(
                "Follow-up optimization request: checking remaining eligible improvements without duplicating staged or aligned settings."
                if is_supplement
                else "Full-game setup request: auditing all applicable settings across game categories."
            ),
            inferred_dimensions=eff_dims,
        )

    if _BROAD_RE.search(lower) or len(dims) >= 3 or (has_saved_prefs and ("based on" in lower or "similar" in lower or "new to" in lower)):
        eff_dims = list(dims)
        if "competitive" in lower or (not eff_dims and not has_saved_prefs):
            for d in DEFAULT_COMPETITIVE_DIMS:
                if d not in eff_dims:
                    eff_dims.append(d)
        elif has_saved_prefs and not eff_dims:
            eff_dims = []  # saved preference weights in ProfileService drive ranking directly
        return ScopePlan(
            scope="broad_optimization",
            max_recs=24,
            auto_stage=True,
            include_minor=True,
            is_supplement=False,
            reason="Broad optimization request: reviewing relevant settings across categories with trade-offs.",
            inferred_dimensions=eff_dims,
        )

    if dims or _ACTION_SEEKING_RE.search(lower):
        return ScopePlan(
            scope="category_optimization",
            max_recs=12,
            auto_stage=True,
            include_minor=False,
            is_supplement=False,
            reason="Goal-targeted request: surfacing all clearly relevant, eligible settings for this goal.",
            inferred_dimensions=dims,
        )

    return ScopePlan(
        scope="explain_only",
        max_recs=0,
        auto_stage=False,
        include_minor=False,
        is_supplement=False,
        reason="No concrete setting goal identified.",
        inferred_dimensions=[],
    )
