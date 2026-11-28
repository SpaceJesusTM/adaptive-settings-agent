"""Deterministic validation of model (or fallback) output. This is the authority boundary.

Every recommendation is checked against the selected game's allowlist, proposability, locks, value domain
(strict: exact options / on-grid numbers), availability on the simulated PC, no-op and duplicates. Text is
trimmed, URLs are removed (no fabricated citations), sentences with unverifiable numeric performance claims
are dropped, and claims that something was already changed are flagged. Nothing here writes state.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..catalog.schema import DIMENSION_LABELS, Setting
from ..domain.store import Store
from ..domain.values import ValueError_, availability_problem, display_value, normalize_value, values_equal
from .intent import classify, is_goal_statement, is_speculative
from .schemas import AssistantDraft
from .objective import Objective, explicit_memory_clauses, interpret_objective, protected_setting_ids, quoted_as_example
from .explain import explanation_target, named_controls

MAX_RECOMMENDATIONS = 3
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
# Targets *claims of measured improvement* ("boosts FPS by 25%", "10 ms lower", "doubles your FPS") rather than
# any number, so plain values such as "a 240 FPS cap" or "144 Hz" are left alone.
_UNIT = r"(?:%|percent\b|fps\b|frames per second\b|ms\b|milliseconds?\b)"
_VERB = (r"(?:increase[sd]?|boost(?:s|ed)?|gain(?:s|ed)?|improv(?:e|es|ed|ement)|raise[sd]?|add(?:s|ed)?|up to|"
         r"reduc(?:e|es|ed|tion)|cut(?:s)?|lower(?:s|ed)?|sav(?:e|es|ed)|by)")
NUMERIC_CLAIM_RE = re.compile(
    rf"\b{_VERB}\b[^.!?]{{0,40}}?\d+(?:\.\d+)?\s*{_UNIT}"
    rf"|\d+(?:\.\d+)?\s*{_UNIT}\s*(?:more|faster|higher|lower|less|better|improvement|boost|gain|increase|reduction)\b"
    r"|\b(?:doubles?|triples?|\d+x)\s+(?:your\s+)?(?:fps|frame ?rate|performance)\b",
    re.I)
CLAIMED_ACTION_RE = re.compile(
    r"\b(?:i|we)(?:['’]ve| have)?\s+(?:already )?(changed|applied|set|updated|turned|enabled|disabled|saved)\b",
    re.I,
)


PLAYER_ACTION_RE = re.compile(
    r"\byou(?:['’]ve| have)? (?:previously |already |just )?(?:adjusted|changed|applied|enabled|disabled|turned)\b", re.I,
)


def _clean(text: Optional[str], limit: int) -> str:
    t = URL_RE.sub("", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _drop_numeric_claims(text: str, notes: list[str], where: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if not NUMERIC_CLAIM_RE.search(s)]
    if len(kept) != len(sentences):
        notes.append(f"Removed an unverifiable numeric performance claim from {where}.")
    return " ".join(kept).strip()


def resolve_setting(store: Store, game: str, ref: str) -> tuple[Optional[Setting], Optional[str]]:
    ref = (ref or "").strip()
    s = store.registry.setting(game, ref)
    if s is not None:
        return s, None
    other = store.registry.find_any_game(ref)
    if other is not None:
        return None, f"'{ref}' is a {other.game.upper()} setting and does not exist in {game.upper()}."
    # Models sometimes return the visible label instead of the id; accept exact label matches only.
    matches = [x for x in store.registry.settings(game) if x.exactLabel.lower() == ref.lower()]
    if len(matches) == 1:
        return matches[0], None
    other_game = [g for g in store.registry.games if g != game]
    for og in other_game:
        if any(x.exactLabel.lower() == ref.lower() for x in store.registry.settings(og)):
            return None, f"'{ref}' is a {og.upper()} label, not a {game.upper()} setting."
    return None, f"'{ref}' is not a setting in the {game.upper()} catalogue."


def validate_draft(
    store: Store,
    game: str,
    draft: AssistantDraft,
    *,
    source: str,
    max_recommendations: int = MAX_RECOMMENDATIONS,
    scope_plan: Optional[Any] = None,
    message: str = "",
    inherit_objective: bool = True,
    focused_setting_id: Optional[str] = None,
    objective_override: Objective | None = None,
    extra_protected: set[str] | None = None,
) -> dict[str, Any]:
    conn = store.connect()
    try:
        values = store.flat_values(conn, game)
        locks = set(store.locks(conn, game))
        hw = store.hardware(conn)
        staged = {r["setting_id"] for r in conn.execute(
            "SELECT i.setting_id FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
            "WHERE p.game = ? AND p.status = 'pending' AND i.status = 'pending'", (game,))}
        session_id = store.session(conn)["sessionId"]
        player_events = {r["setting_id"] for r in conn.execute(
            "SELECT DISTINCT e.setting_id FROM change_events e JOIN change_batches b ON b.id = e.batch_id "
            "WHERE e.game = ? AND b.session_id = ? AND b.undone_by_batch_id IS NULL AND b.source != 'reset'",
            (game, session_id),
        )}
    finally:
        conn.close()

    # Ground "based on ..." in the user's actual stored goals/preferences rather than trusting model text.
    from ..domain.profile import ProfileService  # local import avoids a cycle at module load

    objective = objective_override or interpret_objective(message)
    protected = protected_setting_ids(store, game, message) | (extra_protected or set())
    conn = store.connect()
    try:
        profile = ProfileService(store)
        weights = profile.dimension_weights(conn, game)
        saved_prefs = {(p["dimension"], p["direction"]) for p in profile.applicable_preferences(conn, game)}
        if inherit_objective and (not objective.explicit or not objective.dimensions or getattr(scope_plan, "is_supplement", False)):
            protected.update(profile.objective_protections(conn, game))
    finally:
        conn.close()

    notes: list[str] = []
    filtered: list[dict[str, Any]] = []
    recs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in draft.recommendations:
        s, err = resolve_setting(store, game, r.setting_id)
        base = {"settingRef": r.setting_id, "proposedValue": r.proposed_value}
        if s is None:
            filtered.append({**base, "kind": "unknown_or_wrong_game", "reason": err})
            continue
        if s.id in seen:
            filtered.append({**base, "kind": "duplicate", "reason": f"{s.exactLabel} was suggested twice."})
            continue
        seen.add(s.id)
        if not s.aiProposable or s.controlType in ("keybind", "preset", "color"):
            filtered.append({**base, "settingId": s.id, "kind": "not_proposable",
                             "reason": f"{s.exactLabel} is a personal or hardware-specific setting; the assistant does not propose values for it."})
            continue
        if s.id in protected:
            filtered.append({**base, "settingId": s.id, "kind": "protected_by_request",
                             "reason": f"You asked to keep {s.exactLabel} unchanged."})
            continue
        if s.id in locks:
            filtered.append({**base, "settingId": s.id, "kind": "locked", "reason": f"{s.exactLabel} is locked by you, so it was not suggested."})
            continue
        try:
            value = normalize_value(s, r.proposed_value, strict=True)
        except ValueError_ as exc:
            filtered.append({**base, "settingId": s.id, "kind": "invalid_value", "reason": str(exc)})
            continue
        current = values.get(s.id)
        if values_equal(current, value):
            filtered.append({**base, "settingId": s.id, "kind": "no_op", "reason": f"{s.exactLabel} is already {display_value(s, value)}."})
            continue
        problem = availability_problem(store.registry, s, {**values, s.id: value}, hw)
        if problem:
            filtered.append({**base, "settingId": s.id, "kind": "unavailable", "reason": f"{s.exactLabel}: {problem}"})
            continue
        if s.id in staged:
            filtered.append({**base, "settingId": s.id, "kind": "already_staged", "reason": f"{s.exactLabel} is already in your review tray."})
            continue
        cap = MAX_RECOMMENDATIONS if max_recommendations is None else max_recommendations
        if cap == 0:
            filtered.append({**base, "settingId": s.id, "kind": "over_limit", "reason": "No setting changes were requested for this question."})
            continue
        if len(recs) >= cap:
            reason = "Only the first three suggestions are shown." if cap == 3 else f"Only the first {cap} suggestions are shown."
            filtered.append({**base, "settingId": s.id, "kind": "over_limit", "reason": reason})
            continue
        why = _drop_numeric_claims(_clean(r.why_for_goal, 450), notes, f"the reason for {s.exactLabel}")
        hint_dims = [h.dimension for h in s.goalHints if any(values_equal(value, v) for v in h.prefer)]
        if not why:
            matching = [h for h in s.goalHints if any(values_equal(value, v) for v in h.prefer)]
            why = matching[0].why if matching else "Suggested for your stated goal."
        dim = r.goal_dimension if r.goal_dimension in DIMENSION_LABELS else (hint_dims[0] if hint_dims else None)
        if dim not in weights and hint_dims:
            dim = next((d for d in hint_dims if d in weights), dim)
        based_on = _clean(r.based_on, 200) or None
        stored = [x["text"] for x in weights.get(dim, {}).get("reasons", [])] if dim else []
        if stored and weights.get(dim, {}).get("weight", 0) > 0:
            # Prefer the system's own record of why (session goal / saved preference / simulated context).
            based_on = "; ".join(dict.fromkeys(stored))[:240]
        cross_game = any(x.get("crossGame") for x in weights.get(dim, {}).get("reasons", [])) if dim else False
        recs.append({
            "settingId": s.id, "label": s.exactLabel, "path": s.canonicalPath, "tabId": s.tabId, "subtabId": s.subtabId,
            "currentValue": current, "currentDisplay": display_value(s, current),
            "proposedValue": value, "proposedDisplay": display_value(s, value),
            "whatItDoes": s.description, "whatItDoesSource": s.descriptionSource, "sourceURL": s.sourceURL,
            "verificationStatus": s.verificationStatus,
            "whyForGoal": why,
            "tradeoff": " ".join(filter(None, [
                _drop_numeric_claims(_clean(r.tradeoff_note, 300), notes, f"the trade-off for {s.exactLabel}") or None,
                s.riskOrTradeoffs if s.riskOrTradeoffs and s.riskOrTradeoffs not in (r.tradeoff_note or "") else None])) or None,
            "confidence": r.confidence,
            "dimension": dim, "dimensionLabel": DIMENSION_LABELS.get(dim) if dim else None,
            "basedOn": based_on, "crossGame": cross_game,
            "source": source,
        })

    explanations = []
    for e in draft.explanations[:3]:
        s, err = resolve_setting(store, game, e.setting_id)
        if s is None:
            filtered.append({"settingRef": e.setting_id, "kind": "unknown_explanation_target", "reason": err})
            continue
        text = _drop_numeric_claims(_clean(e.explanation, 700), notes, f"the explanation of {s.exactLabel}")
        explanations.append({"settingId": s.id, "label": s.exactLabel, "path": s.canonicalPath, "tabId": s.tabId,
                             "subtabId": s.subtabId, "explanation": text or s.description,
                             "catalogDescription": s.description, "tradeoffs": s.riskOrTradeoffs,
                             "sourceURL": s.sourceURL, "verificationStatus": s.verificationStatus, "source": source})

    target_text = objective.explanation or (message if draft.intent == "explain" and not recs else "")
    canonical = explanation_target(store, game, target_text, focused_setting_id) if target_text else None
    if canonical and not any(e["settingId"] == canonical.id for e in explanations):
        explanations.append({
            "settingId": canonical.id, "label": canonical.exactLabel, "path": canonical.canonicalPath,
            "tabId": canonical.tabId, "subtabId": canonical.subtabId, "explanation": canonical.description,
            "catalogDescription": canonical.description, "tradeoffs": canonical.riskOrTradeoffs,
            "sourceURL": canonical.sourceURL, "verificationStatus": canonical.verificationStatus, "source": "rules",
        })

    navigate = None
    if canonical or draft.navigate_to:
        if canonical:
            setting, err = canonical, None
        else:
            setting, err = resolve_setting(store, game, draft.navigate_to)
        if setting is None:
            filtered.append({"settingRef": draft.navigate_to, "kind": "unknown_navigation_target", "reason": err})
        else:
            navigate = {"settingId": setting.id, "label": setting.exactLabel, "path": setting.canonicalPath,
                        "tabId": setting.tabId, "subtabId": setting.subtabId}

    speculative = bool(message and (is_speculative(message) or quoted_as_example(message)))
    neutral_explain = bool(
        draft.intent in ("explain", "navigate")
        or (message and classify(message) in ("explain", "navigate") and not is_goal_statement(message))
    )

    prefs = []
    if not speculative and not neutral_explain:
        for p in draft.preference_suggestions[:2]:
            if (p.dimension, p.direction) in saved_prefs:
                notes.append(f"Skipped a suggestion to save “{DIMENSION_LABELS.get(p.dimension, p.dimension)}” — it is already saved.")
                continue
            if p.dimension in DIMENSION_LABELS:
                prefs.append({"dimension": p.dimension, "dimensionLabel": DIMENSION_LABELS[p.dimension], "direction": p.direction,
                              "scope": p.scope, "quote": _clean(p.user_quote, 200), "game": game})
    elif draft.preference_suggestions:
        notes.append("Treated tentative or informational question without proposing preference changes.")

    memory_actions = explicit_memory_clauses(message, game) if not speculative else []
    if getattr(draft, "explicit_memory_actions", None) and not memory_actions:
        notes.append("No directly supported memory instruction was found in the request.")

    # Do not duplicate explicit memory updates inside confirmation chips
    if memory_actions and prefs:
        explicit_dims = {(m["dimension"], m["direction"]) for m in memory_actions if m["kind"] == "preference"}
        prefs = [p for p in prefs if (p["dimension"], p["direction"]) not in explicit_dims]

    reply = _clean(draft.reply, 1800)
    reply = _drop_numeric_claims(reply, notes, "the reply")
    if source == "ai":
        kept = []
        for sentence in re.split(r"(?<=[.!?])\s+", reply):
            action = CLAIMED_ACTION_RE.search(sentence)
            asserted = PLAYER_ACTION_RE.search(sentence)
            controls = {s.id for s in named_controls(store, game, sentence)} if asserted else set()
            unsupported_history = asserted and (
                bool(controls - player_events) if controls else bool(staged) and not (staged & player_events)
            )
            if action and (action[1].lower() != "saved" or not memory_actions) or unsupported_history:
                notes.append("The reply claimed an action. Removed the unverified sentence.")
            else:
                kept.append(sentence)
        reply = " ".join(kept)
    if not reply:
        reply = "Here is what I found." if (recs or explanations or memory_actions) else "I could not produce a reliable answer for that."

    valid_goal_dims = [d for d in dict.fromkeys(draft.goal_dimensions) if d in DIMENSION_LABELS][:5]
    explicit_pref_turn = bool(memory_actions and draft.intent == "preference" and not objective.explicit)
    if speculative or (neutral_explain and not recs and not objective.explicit) or explicit_pref_turn:
        valid_goal_dims = []
    elif not valid_goal_dims and draft.intent != "clarify":
        # Backfill goal dimensions when a local model supplies recommendations or goal phrasing without goal_dimensions.
        candidates_dims: list[str] = []
        if scope_plan is not None:
            candidates_dims.extend(getattr(scope_plan, "inferred_dimensions", []) or [])
        if objective.explicit:
            candidates_dims.extend(objective.dimensions)
        candidates_dims.extend(p["dimension"] for p in prefs if p.get("direction") == "prioritize")
        if draft.intent == "recommend":
            candidates_dims.extend(r["dimension"] for r in recs if r.get("dimension"))
        valid_goal_dims = [d for d in dict.fromkeys(candidates_dims) if d in DIMENSION_LABELS][:5]

    if objective.explicit and objective.dimensions:
        valid_goal_dims = list(getattr(scope_plan, "inferred_dimensions", None) or objective.dimensions)[:5]
    goal_changed = bool(
        objective.explicit
        and valid_goal_dims
        and not speculative
        and not (neutral_explain and not objective.dimensions)
        and not explicit_pref_turn
        and not getattr(scope_plan, "is_supplement", False)
    )

    return {
        "intent": draft.intent,
        "reply": reply,
        "knownsAndUnknowns": _drop_numeric_claims(_clean(draft.knowns_and_unknowns, 450), notes, "the uncertainty note") or None,
        "goalDimensions": valid_goal_dims,
        "goalChanged": goal_changed,
        "objectiveText": objective.text if goal_changed else None,
        "protectedSettingIds": sorted(protected),
        "recommendations": recs,
        "explanations": explanations,
        "navigateTo": navigate,
        "preferenceSuggestions": prefs,
        "explicitMemoryActions": memory_actions,
        "clarifyingQuestion": _clean(draft.clarifying_question, 300) or None,
        "filtered": filtered,
        "validationNotes": notes,
    }


ASKS_FOR_CHANGES_RE = re.compile(
    r"\b(what should i (change|set|do|adjust)|what (can|do) i change|what to change|which settings|what settings|"
    r"set me up|recommend|suggest|change whatever|optimi[sz]e|configure|fresh install|just installed|"
    r"all settings|make (the game|it) (run )?(smoother|faster)|should i (turn|set|enable|disable|change|lower|raise))\b",
    re.I,
)


def needs_repair(
    draft: Optional[AssistantDraft],
    validated: Optional[dict[str, Any]],
    message: str = "",
    *,
    scope_plan: Optional[Any] = None,
    audit: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Return feedback for one repair attempt, or None if the answer is acceptable."""
    if draft is None or validated is None:
        return "The answer was not valid JSON for the required schema."
    if draft.intent == "recommend" and not validated["recommendations"]:
        bad = [f for f in validated["filtered"] if f["kind"] in ("unknown_or_wrong_game", "invalid_value")]
        if bad:
            return "\n".join(f"- {f['reason']}" for f in bad[:5])
    if scope_plan is not None and getattr(scope_plan, "scope", None) == "explain_only":
        return None
    if audit is not None and int(audit.get("eligibleCount", 1)) == 0 and not getattr(scope_plan, "single_setting_hint", False):
        return None
    # The user explicitly asked what to change but got no (valid) recommendation and nothing was blocked for a
    # legitimate reason (lock, already set, unavailable): ask once more for concrete recommendations.
    if (message and ASKS_FOR_CHANGES_RE.search(message) and not validated["recommendations"]
            and draft.intent not in ("clarify", "navigate")
            and not any(f["kind"] in ("locked", "no_op", "unavailable", "already_staged", "not_proposable")
                        for f in validated["filtered"])):
        breadth_note = (
            "grounded recommendations for all eligible improvements from the SETTINGS block"
            if scope_plan and getattr(scope_plan, "max_recs", 3) > 3
            else "1-3 recommendations from the SETTINGS block"
        )
        return (f"The user asked which settings to change. Use intent \"recommend\" and give {breadth_note}, "
                "using the SESSION GOAL / SAVED PREFERENCES as reasons. Do not repeat preferences that "
                "are already saved as preference_suggestions.")
    return None
