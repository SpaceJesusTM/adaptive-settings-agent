"""Deterministic offline fallback responder (NOT AI-generated; always labelled as such in the UI and logs).

It lets the interface be tested without a model and takes over when the local model is unavailable, times
out or returns unusable output. Output goes through the same validator as model output.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..catalog.schema import DIMENSION_LABELS
from ..domain.cross_game import compare_cross_game
from ..domain.planner import build_coverage_audit
from ..domain.profile import ProfileService
from ..domain.store import Store
from .intent import (
    classify,
    detect_dimensions,
    extract_sensitivity_number,
    is_cross_game_query,
    mentioned_setting_terms,
    preference_direction_for,
    preference_scope,
)
from .schemas import AssistantDraft, DraftExplanation, DraftPreference, DraftRecommendation
from .scope import ScopePlan, classify_scope
from .tools import ToolContext, search_settings


def _empty_audit() -> dict[str, Any]:
    return {
        "evaluatedCount": 0,
        "eligibleCount": 0,
        "alreadyAlignedCount": 0,
        "alreadyStagedCount": 0,
        "lockedCount": 0,
        "unavailableCount": 0,
        "manualCount": 0,
        "byCategory": {},
        "manualConsiderations": [],
        "candidates": [],
    }


def fallback_turn(
    store: Store,
    profile: ProfileService,
    game: str,
    message: str,
    ui_state: dict[str, Any],
    *,
    scope_override: Optional[str] = None,
) -> tuple[AssistantDraft, ScopePlan, dict[str, Any]]:
    """Build deterministic fallback draft together with authoritative scope & coverage metadata."""
    intent = classify(message)
    dims = detect_dimensions(message)
    ctx = ToolContext(store=store, profile=profile, game=game, ui_state=ui_state)
    lower = (message or "").lower()

    conn = store.connect()
    try:
        weights = profile.dimension_weights(conn, game)
        has_saved_prefs = bool(profile.preferences(conn))
        scope_plan = classify_scope(
            message,
            detected_dims=dims,
            has_saved_prefs=has_saved_prefs,
            scope_override=scope_override,
        )
        for d in scope_plan.inferred_dimensions:
            entry = weights.setdefault(d, {"weight": 0.0, "reasons": []})
            entry["weight"] = round(entry["weight"] + 1.0, 3)
            entry["reasons"].insert(0, {"kind": "message", "text": "your request in this chat"})
        audit = build_coverage_audit(
            store,
            profile,
            conn,
            game,
            weights=weights,
            scope_plan=scope_plan,
            exclude_staged=True,
            exclude_dismissed=False,
        )
    finally:
        conn.close()

    no_stage_scope = ScopePlan(
        scope="explain_only",
        max_recs=0,
        auto_stage=False,
        include_minor=False,
        is_supplement=False,
        reason=scope_plan.reason,
        inferred_dimensions=dims,
        explicit_override=scope_override,
    )

    if re.search(r"\bwhy (those|these|did you|that)\b", lower):
        return (
            AssistantDraft(
                intent="explain",
                reply=("Basic offline suggestions compare catalogue settings against your stated goals, saved "
                       "preferences, locks, and current values using official documentation priorities first. It "
                       "cannot measure your hardware or FPS."),
            ),
            no_stage_scope,
            audit,
        )

    if intent == "navigate":
        term = mentioned_setting_terms(message) or message
        hits = search_settings(ctx, term, limit=1)["results"]
        if hits:
            return (
                AssistantDraft(
                    intent="navigate",
                    reply=f"It is under {hits[0]['path']}. I've highlighted it in the menu.",
                    navigate_to=hits[0]["id"],
                ),
                no_stage_scope,
                audit,
            )
        return (
            AssistantDraft(
                intent="clarify",
                reply="I could not find a setting with that name in this game's menu.",
                clarifying_question="What is the setting called, or what does it affect?",
            ),
            no_stage_scope,
            audit,
        )

    if is_cross_game_query(message):
        conn_cg = store.connect()
        try:
            cg = compare_cross_game(
                store,
                profile,
                conn_cg,
                query=message,
                current_game=game,
                source_sensitivity=extract_sensitivity_number(message),
            )
        finally:
            conn_cg.close()
        audit["crossGameComparisons"] = cg.get("comparisons", [])
        # Pure comparison question without explicit "change/set up everything" request -> explain & navigate safely
        asking_for_changes = scope_plan.scope in ("broad_optimization", "full_game_setup") and any(
            k in lower for k in ("change", "configure", "set up", "recommend", "suggest")
        )
        if not asking_for_changes or cg.get("comparisons"):
            comps = cg.get("comparisons", [])
            if comps:
                first = comps[0]
                reply_parts = [f"{first['topic']} ({first['relationshipLabel']}): {first['summary']}"]
                conv = first.get("sensitivityConversion")
                if conv and conv.get("convertible"):
                    reply_parts.append(
                        f"360° starting point: {conv['formula']}. {conv['caveats'][0]}"
                    )
                elif conv:
                    reply_parts.append(conv.get("reason", ""))
                elif first.get("safetyNote"):
                    reply_parts.append(first["safetyNote"])
                if asking_for_changes and audit["candidates"]:
                    # Combine cross-game comparison cards with priority-based safe recommendations
                    pass
                else:
                    return (
                        AssistantDraft(
                            intent="explain",
                            reply=" ".join(p for p in reply_parts if p)[:1600],
                            navigate_to=first.get("targetNavigateId"),
                            knowns_and_unknowns=first.get("differences"),
                        ),
                        no_stage_scope,
                        audit,
                    )
            else:
                return (
                    AssistantDraft(
                        intent="clarify",
                        reply=cg.get("note", "No matching cross-game comparison found."),
                        clarifying_question="Ask about push-to-talk, mouse sensitivity, abilities vs. grenades, movement keys, crosshairs, or V-Sync/Reflex/clarity.",
                    ),
                    no_stage_scope,
                    audit,
                )

    if intent == "explain":
        term = mentioned_setting_terms(message) or message
        hits = search_settings(ctx, term, limit=2)["results"]
        if hits:
            s = store.registry.setting(game, hits[0]["id"])
            text = s.description + (f" Trade-off: {s.riskOrTradeoffs}" if s and s.riskOrTradeoffs else "")
            return (
                AssistantDraft(
                    intent="explain",
                    reply=f"Here is what the catalogue says about {s.exactLabel} ({s.canonicalPath}).",
                    explanations=[DraftExplanation(setting_id=s.id, explanation=text)],
                    navigate_to=s.id,
                ),
                no_stage_scope,
                audit,
            )
        return (
            AssistantDraft(
                intent="clarify",
                reply="I could not match that to a setting in this game.",
                clarifying_question="Which setting do you mean?",
            ),
            no_stage_scope,
            audit,
        )

    if intent == "preference":
        prefs = [
            DraftPreference(
                dimension=d,
                direction=preference_direction_for(message, d),
                scope=preference_scope(message),
                user_quote=message[:180],
            )
            for d in dims[:2]
        ]
        if prefs:
            names = ", ".join(
                f"{'more' if p.direction == 'prioritize' else 'less'} weight on {DIMENSION_LABELS[p.dimension]}"
                for p in prefs
            )
            scope = "for this session" if prefs[0].scope == "session" else "as a lasting preference"
            return (
                AssistantDraft(
                    intent="preference",
                    reply=f"I can record {names} {scope}. Confirm below if that is right.",
                    goal_dimensions=[p.dimension for p in prefs if p.direction == "prioritize"],
                    preference_suggestions=prefs,
                ),
                no_stage_scope,
                audit,
            )
        return (
            AssistantDraft(
                intent="clarify",
                reply="I did not recognise which aspect you care about.",
                clarifying_question="Do you mean performance, input latency, visibility, audio or something else?",
            ),
            no_stage_scope,
            audit,
        )

    # Focused single-setting question (e.g., "Should I turn off VSync?")
    if scope_plan.single_setting_hint:
        term = mentioned_setting_terms(message) or message
        hits = search_settings(ctx, term, limit=2)["results"]
        hit_ids = [h["id"] for h in hits]
        cand_map = {c["settingId"]: c for c in audit["candidates"]}
        picked = next((cand_map[sid] for sid in hit_ids if sid in cand_map), None)
        if picked is not None:
            recs = [
                DraftRecommendation(
                    setting_id=picked["settingId"],
                    proposed_value=str(picked["targetValue"]),
                    why_for_goal=picked["why"],
                    tradeoff_note=picked["tradeoff"],
                    confidence="medium" if picked["whyBasis"] == "official" else "low",
                    goal_dimension=picked["dimension"],
                    based_on="; ".join(picked["basedOn"][:2]) or "your request in this chat",
                )
            ]
            return (
                AssistantDraft(
                    intent="recommend",
                    goal_dimensions=[picked["dimension"]],
                    recommendations=recs,
                    reply=(
                        f"Prepared {picked['label']} ({picked['currentDisplay']} -> {picked['targetDisplay']}) "
                        f"for review in Changes. {picked['why']}"
                    ),
                    knowns_and_unknowns="Offline suggestions cannot measure your PC; review and revert if needed.",
                ),
                scope_plan,
                audit,
            )
        if hits:
            s = store.registry.setting(game, hits[0]["id"])
            if s is not None:
                from ..domain.values import availability_problem, values_equal

                conn = store.connect()
                try:
                    vals = store.flat_values(conn, game)
                    is_locked = store.is_locked(conn, game, s.id)
                    hw = store.hardware(conn)
                finally:
                    conn.close()
                cur_val = vals.get(s.id)
                prob = availability_problem(store.registry, s, vals, hw)
                if s.aiProposable and not is_locked and not prob and s.goalHints:
                    comp_order = ["input_latency", "performance", "visibility", "audio_awareness", "focus", "network_stability"]
                    wants_off = any(w in lower for w in ("turn off", "disable"))
                    candidates_hints = sorted(
                        s.goalHints,
                        key=lambda h: (0 if h.basis == "official" else 1, comp_order.index(h.dimension) if h.dimension in comp_order else 99),
                    )
                    for h in candidates_hints:
                        for pref_val in h.prefer:
                            if wants_off and str(pref_val) not in ("off", "0"):
                                continue
                            if not values_equal(cur_val, pref_val):
                                recs = [
                                    DraftRecommendation(
                                        setting_id=s.id,
                                        proposed_value=str(pref_val),
                                        why_for_goal=h.why,
                                        tradeoff_note=s.riskOrTradeoffs,
                                        confidence="medium" if h.basis == "official" else "low",
                                        goal_dimension=h.dimension,
                                        based_on="your request in this chat",
                                    )
                                ]
                                return (
                                    AssistantDraft(
                                        intent="recommend",
                                        goal_dimensions=[h.dimension],
                                        recommendations=recs,
                                        reply=f"Prepared {s.exactLabel} ({hits[0]['current']} -> {pref_val}) for review in Changes. {h.why}",
                                        knowns_and_unknowns="Offline suggestions cannot measure your PC; review and revert if needed.",
                                    ),
                                    scope_plan,
                                    audit,
                                )
                text = s.description + (f" Trade-off: {s.riskOrTradeoffs}" if s.riskOrTradeoffs else "")
                return (
                    AssistantDraft(
                        intent="explain",
                        reply=f"{s.exactLabel} is already aligned, locked, or personal preference (currently {hits[0]['current']}).",
                        explanations=[DraftExplanation(setting_id=s.id, explanation=text)],
                        navigate_to=s.id,
                    ),
                    scope_plan,
                    audit,
                )

    eff_dims = scope_plan.inferred_dimensions or list(dims)
    if scope_plan.scope != "explain_only" and (intent == "recommend" or eff_dims or has_saved_prefs):
        selected = audit["candidates"][: scope_plan.max_recs]
        goal = ", ".join(DIMENSION_LABELS[d] for d in eff_dims) if eff_dims else "your saved preferences"
        if not selected:
            summary_bits = [f"Evaluated {audit['evaluatedCount']} settings: {audit['alreadyAlignedCount']} already aligned"]
            if audit["alreadyStagedCount"]:
                summary_bits.append(f"{audit['alreadyStagedCount']} already staged")
            if audit["lockedCount"]:
                summary_bits.append(f"{audit['lockedCount']} locked")
            return (
                AssistantDraft(
                    intent="recommend",
                    goal_dimensions=eff_dims[:5],
                    reply=f"{', '.join(summary_bits)}. No additional changes are needed for {goal}.",
                    knowns_and_unknowns="Offline suggestions cannot measure your PC; they compare against catalogue goals and locks.",
                ),
                scope_plan,
                audit,
            )
        recs = [
            DraftRecommendation(
                setting_id=c["settingId"],
                proposed_value=str(c["targetValue"]),
                why_for_goal=c["why"],
                tradeoff_note=c["tradeoff"],
                confidence="medium" if c["whyBasis"] == "official" else "low",
                goal_dimension=c["dimension"],
                based_on="; ".join(c["basedOn"][:2]) or "your request in this chat",
            )
            for c in selected
        ]
        cats = list(dict.fromkeys(c["category"] for c in selected))
        cat_text = ", ".join(cats[:4]) + ("…" if len(cats) > 4 else "")
        return (
            AssistantDraft(
                intent="recommend",
                goal_dimensions=eff_dims[:5],
                recommendations=recs,
                reply=(
                    f"Reviewed {audit['evaluatedCount']} settings for {goal} and prepared {len(recs)} change(s) "
                    f"across {cat_text} ({audit['alreadyAlignedCount']} already aligned). Nothing has been applied yet."
                ),
                knowns_and_unknowns="Offline suggestions cannot measure your hardware; review each item and revert anything that does not help.",
            ),
            scope_plan,
            audit,
        )

    return (
        AssistantDraft(
            intent="clarify",
            reply="I can suggest settings for goals like smoother frame rate, lower input latency, clearer player visibility or hearing footsteps.",
            clarifying_question="What would you like to improve?",
        ),
        no_stage_scope,
        audit,
    )


def fallback_draft(
    store: Store,
    profile: ProfileService,
    game: str,
    message: str,
    ui_state: dict[str, Any],
    *,
    scope_override: Optional[str] = None,
) -> AssistantDraft:
    draft, _, _ = fallback_turn(store, profile, game, message, ui_state, scope_override=scope_override)
    return draft
