"""Shared interpretation of current objectives and explicit setting exclusions."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .intent import detect_dimensions, detect_explicit_memory, is_goal_statement, is_speculative

_SPLIT = re.compile(
    r"[.!?;]+(?:\s+|$)|,?\s+\b(?:but|also|and)\s+(?="
    r"(?:tonight|today|for now|for this session|i still (?:need|want)|explain|tell me|remember|keep\b|leave\b|don['’]t\b|do not\b))",
    re.I,
)
_ACCEPTED_COST = re.compile(
    r"\b(?:(?:i (?:can|could|am willing to)|i['’]m willing to)\s+)?"
    r"(?:give up|sacrifice|trade|lose|accept)\s+[^.!?;]{1,90}?\s+(?:if|for|to)\s+",
    re.I,
)
_CURRENT = re.compile(r"\b(?:today|tonight|for now|this session|right now)\b", re.I)
_DURABLE_OR_PREFERENCE = re.compile(
    r"^\s*(?:also\s+)?(?:remember|from now on|don't forget|keep in mind|"
    r"i\s+(?:normally|usually|always|prefer|value|would rather|care more|don['’]t (?:really )?care|do not (?:really )?care))\b",
    re.I,
)
_NOT_OBJECTIVE = re.compile(r"^\s*(?:also\s+)?(?:keep|leave|don['’]t|do not|avoid|everything except|"
    r"i (?:want|need) to keep|that recommendation was wrong)\b", re.I)
_TEMPORARY_END = re.compile(
    r"^\s*(?:(?:actually|okay|ok|now)[, ]+)?(?:"
    r"(?:clear|end|drop|stop|forget)(?:\s+about)?\s+(?:my |the |this |that )?(?:temporary |current |session )?(?:goal|objective)"
    r"|(?:go |switch |return )?back to (?:my |the )?usual (?:priorities|preferences)"
    r")\s*[.!?]*$", re.I,
)
_PROTECT = re.compile(
    r"\b(?:keep|leave|preserve)\s+(?P<keep>[^.!?;]{1,155}?)\s+"
    r"(?:unchanged|as (?:it|they) (?:is|are)|exactly as (?:it|they) (?:is|are)|the same|alone)\b"
    r"|\b(?:i (?:want|need) to keep|keep) (?P<shadows>(?:my |the )?(?:global |dynamic )?shadows)\s+because\b"
    r"|\b(?:(?:don['’]t|do not|never)\s+(?:change|touch|adjust|modify)|"
    r"without\s+(?:changing|touching|adjusting|modifying))\s+(?P<avoid>[^.!?;]{1,110})"
    r"|\b(?P<only>(?:only\s+(?:change|adjust|configure|touch)|configure)\s+(?:the\s+)?"
    r"(?:graphics|video)(?: and frame[- ]pacing)?(?:\s+settings)?)\b",
    re.I,
)
_END_PROTECTION = re.compile(r",?\s+(?:and |also )?(?:explain|tell me|remember|but|then)\b", re.I)


@dataclass(frozen=True)
class Objective:
    text: str
    dimensions: list[str]
    explanation: str | None
    clear: bool
    explicit: bool


_QUOTE = re.compile(r""" "[^"\n]+" | “[^”\n]+” | (?<!\w)'[^'\n]+'(?!\w) """, re.X)
_QUOTED_EXAMPLE = re.compile(r"\b(?:example|hypothetical|quote|someone wrote|someone said|imagine someone|suppose someone|what if someone)\b", re.I)


def quoted_as_example(message: str) -> bool:
    return bool(_QUOTE.search(message) and _QUOTED_EXAMPLE.search(_QUOTE.sub("", message)))


def interpret_objective(message: str) -> Objective:
    if quoted_as_example(message):
        return Objective("", [], None, False, False)
    clauses = [part.strip(" ,") for part in _SPLIT.split(message.strip()) if part.strip(" ,")]
    clear = bool(_TEMPORARY_END.fullmatch(message))
    explanation = next((p for p in clauses if re.match(r"^(?:also\s+)?(?:explain|tell me what)\b", p, re.I)), None)
    current = [
        p for p in clauses
        if not _NOT_OBJECTIVE.search(p)
        and not re.match(r"^(?:also\s+)?(?:and\s+)?(?:explain|tell me what|where|why|what does|what are the downsides)\b", p, re.I)
        and (not _DURABLE_OR_PREFERENCE.search(p) or _CURRENT.search(p))
    ]
    text = ". ".join(current)
    positive = []
    for clause in current:
        cost = _ACCEPTED_COST.search(clause)
        if cost and detect_dimensions(clause[cost.end():]):
            clause = clause[:cost.start()] + clause[cost.end():]
        positive.append(re.split(r"\b(?:willing to sacrifice|at the cost of|at the expense of)\b", clause,
                                 maxsplit=1, flags=re.I)[0])
    dims = detect_dimensions(". ".join(positive))
    explicit = bool(text and not clear and not is_speculative(text) and is_goal_statement(text, dims))
    return Objective(text, dims, explanation, clear, explicit)


def objective_takes_precedence(text: str) -> bool:
    return bool(_CURRENT.search(text) or re.search(r"\b(configure|optimi[sz]e|make|set me up|instead)\b", text, re.I))


def protected_setting_ids(store, game: str, message: str) -> set[str]:
    settings = store.registry.settings(game)
    matches = list(_PROTECT.finditer(message))
    protected: set[str] = set()
    if quoted_as_example(message):
        return protected
    for match in matches:
        if match["only"]:
            protected.update(s.id for s in settings if s.tabId != "video" or s.controlType == "preset")
            continue
        terms = _END_PROTECTION.split(match["keep"] or match["avoid"] or match["shadows"], maxsplit=1)[0].lower()
        for s in settings:
            label = s.exactLabel.lower()
            if (
                (len(label) >= 4 and re.search(rf"(?<!\w){re.escape(label)}(?!\w)", terms))
                or ("resolution" in terms and "resolution" in label)
                or ("aspect ratio" in terms and "aspect ratio" in label)
                or (re.search(r"anti[ -]?aliasing|\bmsaa\b", terms)
                    and ("anti-aliasing" in label or s.key == "msaa"))
                or (re.search(r"\b(?:graphics|video) settings\b", terms) and s.tabId == "video")
                or (("aim feel" in terms or "feel of aiming" in terms or "aiming feels" in terms)
                    and ("sensitivity" in label or s.controlType == "keybind" or ".crosshair." in s.id))
                or ("sensitivity" in terms and "sensitivity" in label)
                or (re.fullmatch(r"(?:my |the )?(?:global |dynamic )?shadows", terms.strip())
                    and "shadow" in label and ("global" not in terms or "global" in label)
                    and ("dynamic" not in terms or "dynamic" in label))
                or ("crosshair" in terms and (s.tabId == "crosshair" or ".crosshair." in s.id))
                or (re.search(r"\baudio\b|\bsound settings\b", terms) and s.tabId == "audio")
                or (re.search(r"\b(?:controls|keybinds|key bindings)\b", terms)
                    and (s.controlType == "keybind" or s.tabId in {"controls", "kbmouse"}
                         or "sensitivity" in label))
            ):
                protected.add(s.id)
    return protected


def prepare_objective(store, profile, conn, game: str, message: str, scope_override: str | None):
    from .scope import classify_scope

    objective = interpret_objective(message)
    scope_plan = classify_scope(
        objective.text or message,
        detected_dims=objective.dimensions,
        has_saved_prefs=bool(profile.applicable_preferences(conn, game)),
        scope_override=scope_override,
    )
    if quoted_as_example(message):
        scope_plan = replace(scope_plan, scope="explain_only", auto_stage=False, max_recs=0, inferred_dimensions=[])
    elif re.search(r"\b(?:inspect|find something|show me where|help me understand)\b", message, re.I) and re.search(
        r"\b(?:without changing|don't change|do not change)\b", message, re.I
    ):
        scope_plan = replace(scope_plan, scope="explain_only", auto_stage=False, max_recs=0)
    if objective.dimensions and any(match["only"] for match in _PROTECT.finditer(message)):
        scope_plan = replace(scope_plan, inferred_dimensions=objective.dimensions)
    # A fresh task starts from applicable preferences. The preceding objective remains active
    # for follow-ups until replaced or cleared.
    new_objective = objective.explicit and bool(scope_plan.inferred_dimensions) and not scope_plan.is_supplement
    weights = profile.dimension_weights(conn, game, include_objective=not new_objective)
    if new_objective:
        profile.prioritize_objective(weights, scope_plan.inferred_dimensions, "your request in this chat",
                                     takes_precedence=objective_takes_precedence(objective.text))
    protected = protected_setting_ids(store, game, message)
    if not new_objective:
        protected.update(profile.objective_protections(conn, game))
    return objective, scope_plan, weights, protected


def explicit_memory_clauses(message: str, game: str) -> list[dict]:
    """Persist only values and preferences that can be grounded directly in the user's words."""
    actions = {}
    if quoted_as_example(message):
        return []
    for clause in _SPLIT.split(message.replace("’", "'")):
        clause = re.sub(r"^\s*(?:and |also )+", "", clause, flags=re.I)
        leading_scope = re.match(r"^for (valorant|cs2),\s*(.*)", clause, re.I)
        evidence_clause = clause
        if leading_scope:
            clause = f"{leading_scope[2]} in {leading_scope[1]}"
        # A quoted or embedded request is insufficient evidence to save anything.
        if not re.match(r"^\s*(?:please\s+)?(?:remember|don['’]t forget|from now on|i always|always)\b", clause, re.I):
            continue
        if re.search(r"\b(?:might|maybe|not sure|considering)\b", clause, re.I):
            continue
        named_scope = re.findall(r"\b(?:in|for)\s+(valorant|cs2)\b", clause, re.I)
        if len(set(name.lower() for name in named_scope)) > 1:
            continue
        extracted = detect_explicit_memory(clause, game)
        style = re.fullmatch(
            r"(?:please )?remember(?: that)? i (?:prefer|use|like) (?:a |my )?"
            r"([a-z]+(?: [a-z]+){0,4}) crosshair(?: (?:in|for) (?:valorant|cs2))?",
            clause.strip(), re.I,
        )
        style_words = {"small", "large", "green", "red", "white", "cyan", "pink", "yellow", "blue",
                       "static", "dynamic", "black", "purple", "thin", "thick", "outlined", "dot"}
        if style and set(style[1].lower().split()) <= style_words:
            extracted = [{"kind": "fact", "factKey": "crosshair_style", "valueText": style[1].lower(),
                          "scope": "durable", "game": named_scope[0].lower() if named_scope else game,
                          "quote": clause[:180]}]
        statement = re.sub(r"^(?:please )?(?:remember(?: that)?|from now on)\s+", "", clause.strip(), flags=re.I)
        voice = re.fullmatch(
            r"i\s+(?:always\s+)?(?:use|prefer|keep)\s+"
            r"(push[ -]to[ -]talk|push[ -]to[ -]use mic|voice activation|open mic(?:rophone)?|automatic voice)"
            r"(?:\s+(?:in|for)\s+(valorant|cs2))?", statement, re.I,
        )
        if voice and not _CURRENT.search(clause):
            named_game = voice[2].lower() if voice[2] else game
            mode = "Push To Talk" if voice[1].lower().startswith("push") else (
                "Automatic" if named_game == "valorant" else "Open Microphone"
            )
            extracted = [{"kind": "fact", "factKey": "voice_activation", "valueText": mode,
                          "scope": "durable", "game": named_game, "quote": clause[:180]}]
        for action in extracted:
            if action["kind"] == "fact" and _CURRENT.search(clause):
                continue
            if action["kind"] == "preference":
                action["appliesToGame"] = named_scope[0].lower() if named_scope else None
            action["quote"] = evidence_clause.strip()[:180]
            key = (action.get("dimension") or action.get("factKey"), action.get("appliesToGame"), action["game"], action["scope"])
            actions[key] = action
    return list(actions.values())[:3]


def preference_removal(message: str) -> tuple[str, str | None] | None:
    """Recognize a narrowly phrased withdrawal of one remembered dimension."""
    match = re.fullmatch(
        r"\s*(?:actually[, ]+)?forget (?:what i said about|my (?:saved )?preference for) (.+?)[.!]?\s*",
        message, re.I,
    )
    if not match:
        return None
    topic = match[1]
    dimensions = detect_dimensions(topic)
    scope = re.findall(r"\b(?:in|for)\s+(valorant|cs2)\b", topic, re.I)
    if len(dimensions) != 1 or len(set(name.lower() for name in scope)) > 1:
        return None
    return dimensions[0], scope[0].lower() if scope else None
