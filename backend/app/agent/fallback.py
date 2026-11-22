"""Deterministic offline fallback responder (NOT AI-generated; always labelled as such in the UI and logs).

It lets the interface be tested without a model and takes over when the local model is unavailable, times
out or returns unusable output. Output goes through the same validator as model output.
"""
from __future__ import annotations

import re
from typing import Any

from ..catalog.schema import DIMENSION_LABELS
from ..domain.profile import ProfileService
from ..domain.recommender import rank_candidates
from ..domain.store import Store
from .intent import classify, detect_dimensions, mentioned_setting_terms, preference_direction_for, preference_scope
from .schemas import AssistantDraft, DraftExplanation, DraftPreference, DraftRecommendation
from .tools import ToolContext, search_settings


def fallback_draft(store: Store, profile: ProfileService, game: str, message: str, ui_state: dict[str, Any]) -> AssistantDraft:
    intent = classify(message)
    dims = detect_dimensions(message)
    ctx = ToolContext(store=store, profile=profile, game=game, ui_state=ui_state)
    lower = (message or "").lower()

    if re.search(r"\bwhy (those|these|did you|that)\b", lower):
        return AssistantDraft(
            intent="explain",
            reply=("The offline fallback ranks settings with a fixed rule: each catalogue setting carries goal tags "
                   "(for example 'performance' or 'input latency'); settings whose current value does not yet match "
                   "your stated goal or saved preferences score higher, and reasons backed by official game "
                   "documentation rank above editorial ones. It cannot measure your PC."),
        )

    if intent == "navigate":
        term = mentioned_setting_terms(message) or message
        hits = search_settings(ctx, term, limit=1)["results"]
        if hits:
            return AssistantDraft(intent="navigate", reply=f"It is under {hits[0]['path']}. I've highlighted it in the menu.",
                                  navigate_to=hits[0]["id"])
        return AssistantDraft(intent="clarify", reply="I could not find a setting with that name in this game's menu.",
                              clarifying_question="What is the setting called, or what does it affect?")

    if intent == "explain":
        term = mentioned_setting_terms(message) or message
        hits = search_settings(ctx, term, limit=2)["results"]
        if hits:
            s = store.registry.setting(game, hits[0]["id"])
            text = s.description + (f" Trade-off: {s.riskOrTradeoffs}" if s and s.riskOrTradeoffs else "")
            return AssistantDraft(intent="explain", reply=f"Here is what the catalogue says about {s.exactLabel} ({s.canonicalPath}).",
                                  explanations=[DraftExplanation(setting_id=s.id, explanation=text)], navigate_to=s.id)
        return AssistantDraft(intent="clarify", reply="I could not match that to a setting in this game.",
                              clarifying_question="Which setting do you mean?")

    if intent == "preference":
        prefs = [DraftPreference(dimension=d, direction=preference_direction_for(message, d), scope=preference_scope(message),
                                 user_quote=message[:180]) for d in dims[:2]]
        if prefs:
            names = ", ".join(f"{'more' if p.direction == 'prioritize' else 'less'} weight on {DIMENSION_LABELS[p.dimension]}" for p in prefs)
            scope = "for this session" if prefs[0].scope == "session" else "as a lasting preference"
            return AssistantDraft(intent="preference", reply=f"I can record {names} {scope}. Confirm below if that is right.",
                                  goal_dimensions=[p.dimension for p in prefs if p.direction == "prioritize"],
                                  preference_suggestions=prefs)
        return AssistantDraft(intent="clarify", reply="I did not recognise which aspect you care about.",
                              clarifying_question="Do you mean performance, input latency, visibility, audio or something else?")

    if intent == "recommend" and dims:
        conn = store.connect()
        try:
            weights = profile.dimension_weights(conn, game)
            for d in dims:
                entry = weights.setdefault(d, {"weight": 0.0, "reasons": []})
                entry["weight"] = round(entry["weight"] + 1.0, 3)
                entry["reasons"].insert(0, {"kind": "message", "text": "your request in this chat"})
            cands = rank_candidates(store, profile, conn, game, weights=weights, limit=3)
        finally:
            conn.close()
        goal = ", ".join(DIMENSION_LABELS[d] for d in dims)
        if not cands:
            return AssistantDraft(intent="recommend", goal_dimensions=dims,
                                  reply=f"Your current settings already match the catalogue's suggestions for {goal}, "
                                        "or the relevant settings are locked or unavailable.",
                                  knowns_and_unknowns="The fallback cannot measure your PC; it only compares settings with catalogue goal tags.")
        recs = [DraftRecommendation(setting_id=c["settingId"], proposed_value=str(c["targetValue"]), why_for_goal=c["why"],
                                    tradeoff_note=None, confidence="medium" if c["whyBasis"] == "official" else "low",
                                    goal_dimension=c["dimension"], based_on="; ".join(c["basedOn"][:2])) for c in cands]
        return AssistantDraft(
            intent="recommend", goal_dimensions=dims, recommendations=recs,
            reply=(f"Rule-based suggestions for {goal}: {len(recs)} setting(s) whose catalogue goal tags match and whose "
                   "current value differs. Review them below; nothing changes until you apply."),
            knowns_and_unknowns="These rules cannot measure your hardware; test after each change and revert anything that does not help.",
        )

    return AssistantDraft(
        intent="clarify",
        reply="I can suggest settings for goals like smoother frame rate, lower input latency, clearer player visibility or hearing footsteps.",
        clarifying_question="What would you like to improve?",
    )
