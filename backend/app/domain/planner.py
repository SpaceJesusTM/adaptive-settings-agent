"""Full-catalogue coverage planner for scope-aware recommendation generation.

Evaluates every setting in the game's canonical catalogue against the user's weighted dimensions,
current values, locks, staged items, availability rules, and proposability boundaries. Produces an
inspectable coverage ledger so broad/full-setup responses never fabricate totals or sneak personal
controls into AI proposals.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..agent.scope import ScopePlan
from ..catalog.schema import DIMENSION_LABELS, Setting
from ..domain.profile import ProfileService
from ..domain.store import Store
from ..domain.values import availability_problem, display_value, values_equal

BASIS_FACTOR = {"official": 1.0, "editorial": 0.85}


def _first_valid_target(prefer: list[Any], current: Any) -> Any:
    for v in prefer:
        if not values_equal(v, current):
            return v
    return None


def _manual_reason(s: Setting) -> str:
    if s.controlType == "keybind":
        return "Key bindings are personal ergonomics and are never modified by AI suggestions."
    if s.controlType == "preset":
        return "Video presets overwrite multiple settings at once; inspect individual settings instead."
    if s.controlType == "color":
        return "Crosshair and HUD colors are personal visual preference."
    if not s.rangeVerified:
        return "Slider range is prototype-only (not officially documented), so the assistant explains rather than proposing a number."
    if s.optionsSimulated:
        return "Options depend on your physical display or audio hardware."
    return "Personal or hardware-specific setting — adjust manually if needed."


def build_coverage_audit(
    store: Store,
    profile: ProfileService,
    conn: sqlite3.Connection,
    game: str,
    *,
    weights: dict[str, dict[str, Any]],
    scope_plan: ScopePlan,
    exclude_staged: bool = True,
    exclude_dismissed: bool = False,
) -> dict[str, Any]:
    """Audit the entire game catalogue against active goal weights and safety boundaries."""
    positive = {d: w for d, w in weights.items() if w["weight"] > 0}
    values = store.flat_values(conn, game)
    locked_set = set(store.locks(conn, game))
    hw = store.hardware(conn)
    staged_set = {
        r["setting_id"]
        for r in conn.execute(
            "SELECT i.setting_id FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
            "WHERE p.game = ? AND p.status = 'pending' AND i.status = 'pending'",
            (game,),
        )
    } if exclude_staged else set()
    sig = ProfileService.signature(weights)
    dismissed_set = {
        r["setting_id"]
        for r in conn.execute(
            "SELECT setting_id FROM dismissals WHERE game = ? AND signature = ?",
            (game, sig),
        )
    } if exclude_dismissed else set()

    candidates: list[dict[str, Any]] = []
    already_aligned: list[dict[str, Any]] = []
    already_staged: list[dict[str, Any]] = []
    locked_items: list[dict[str, Any]] = []
    unavailable_items: list[dict[str, Any]] = []
    manual_considerations: list[dict[str, Any]] = []
    by_category: dict[str, dict[str, int]] = {}
    evaluated_count = 0
    not_relevant_count = 0

    for s in store.registry.settings(game):
        evaluated_count += 1
        cat_bucket = by_category.setdefault(
            s.category,
            {
                "evaluated": 0,
                "eligible": 0,
                "alreadyAligned": 0,
                "alreadyStaged": 0,
                "locked": 0,
                "unavailable": 0,
                "manual": 0,
            },
        )
        cat_bucket["evaluated"] += 1
        current = values.get(s.id)

        # Check whether this setting relates to any positive goal dimension (via hints or tags).
        relevant_hints = [h for h in s.goalHints if h.dimension in positive]
        relevant_tags = [t for t in s.goalTags if t in positive]

        if not s.aiProposable or s.controlType in ("keybind", "preset"):
            if relevant_hints or relevant_tags:
                cat_bucket["manual"] += 1
                manual_considerations.append(
                    {
                        "settingId": s.id,
                        "label": s.exactLabel,
                        "path": s.canonicalPath,
                        "category": s.category,
                        "currentDisplay": display_value(s, current),
                        "reason": _manual_reason(s),
                        "whatItDoes": s.description,
                        "tradeoffs": s.riskOrTradeoffs,
                    }
                )
            else:
                not_relevant_count += 1
            continue

        if not relevant_hints:
            not_relevant_count += 1
            continue

        if s.id in locked_set:
            cat_bucket["locked"] += 1
            locked_items.append({"settingId": s.id, "label": s.exactLabel, "path": s.canonicalPath})
            continue

        if s.id in staged_set:
            cat_bucket["alreadyStaged"] += 1
            already_staged.append({"settingId": s.id, "label": s.exactLabel, "path": s.canonicalPath})
            continue

        if s.id in dismissed_set:
            not_relevant_count += 1
            continue

        prob = availability_problem(store.registry, s, values, hw)
        if prob:
            cat_bucket["unavailable"] += 1
            unavailable_items.append({"settingId": s.id, "label": s.exactLabel, "reason": prob})
            continue

        # Score candidate hints against current value
        scored: list[tuple[float, Any, Any]] = []
        satisfied_dims: list[str] = []
        skipped_minor = False
        for h in relevant_hints:
            w = positive[h.dimension]["weight"]
            if any(values_equal(current, v) for v in h.prefer):
                satisfied_dims.append(h.dimension)
                continue
            target = _first_valid_target(h.prefer, current)
            if target is None:
                continue
            if not scope_plan.include_minor and h.basis == "editorial" and w < 0.8 and s.verificationStatus == "secondary-only":
                skipped_minor = True
                continue
            scored.append((w * BASIS_FACTOR.get(h.basis, 0.8), h, target))

        if not scored:
            if satisfied_dims or not skipped_minor:
                cat_bucket["alreadyAligned"] += 1
                already_aligned.append(
                    {
                        "settingId": s.id,
                        "label": s.exactLabel,
                        "path": s.canonicalPath,
                        "currentDisplay": display_value(s, current),
                    }
                )
            else:
                not_relevant_count += 1
            continue

        scored.sort(key=lambda t: -t[0])
        best_score, best_hint, target = scored[0]

        # Do not override a higher-or-equal priority dimension that the current value already satisfies
        if any(positive[d]["weight"] >= positive[best_hint.dimension]["weight"] for d in satisfied_dims):
            cat_bucket["alreadyAligned"] += 1
            already_aligned.append(
                {
                    "settingId": s.id,
                    "label": s.exactLabel,
                    "path": s.canonicalPath,
                    "currentDisplay": display_value(s, current),
                }
            )
            continue

        conflicts = []
        for h in s.goalHints:
            if h.dimension == best_hint.dimension:
                continue
            w_other = weights.get(h.dimension, {}).get("weight", 0.0)
            prefers_target = any(values_equal(target, v) for v in h.prefer)
            if w_other > 0 and not prefers_target:
                conflicts.append(f"You also prioritize {DIMENSION_LABELS[h.dimension]}: {h.why}")
            if w_other < 0 and prefers_target:
                best_score += w_other
        if best_score <= 0:
            cat_bucket["alreadyAligned"] += 1
            continue

        reasons = weights[best_hint.dimension]["reasons"]
        cat_bucket["eligible"] += 1
        candidates.append(
            {
                "settingId": s.id,
                "label": s.exactLabel,
                "path": s.canonicalPath,
                "tabId": s.tabId,
                "category": s.category,
                "currentValue": current,
                "currentDisplay": display_value(s, current),
                "targetValue": target,
                "targetDisplay": display_value(s, target),
                "score": round(best_score, 3),
                "dimension": best_hint.dimension,
                "dimensionLabel": DIMENSION_LABELS[best_hint.dimension],
                "whatItDoes": s.description,
                "whatItDoesSource": s.descriptionSource,
                "why": best_hint.why,
                "whyBasis": best_hint.basis,
                "basedOn": [r["text"] for r in reasons],
                "crossGame": any(r.get("crossGame") for r in reasons),
                "tradeoff": " ".join(filter(None, [s.riskOrTradeoffs] + conflicts)) or None,
                "sourceURL": s.sourceURL,
                "verificationStatus": s.verificationStatus,
                "order": s.order,
            }
        )

    candidates.sort(key=lambda c: (-c["score"], c["order"]))
    return {
        "evaluatedCount": evaluated_count,
        "eligibleCount": len(candidates),
        "alreadyAlignedCount": len(already_aligned),
        "alreadyStagedCount": len(already_staged),
        "lockedCount": len(locked_items),
        "unavailableCount": len(unavailable_items),
        "manualCount": len(manual_considerations),
        "notRelevantCount": not_relevant_count,
        "byCategory": by_category,
        "candidates": candidates,
        "alreadyAlignedItems": already_aligned[:30],
        "alreadyStagedItems": already_staged,
        "lockedItems": locked_items,
        "unavailableItems": unavailable_items[:15],
        "manualConsiderations": manual_considerations[:15],
    }
