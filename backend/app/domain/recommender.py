"""Deterministic, inspectable ranking of catalogue settings against the user's goals and preferences.

Score(setting) = sum over its goal hints of weight(dimension) x basis factor, counted only when the current
value does not already satisfy the hint. When two weighted dimensions want different values (e.g. CS2
Boost Player Contrast: visibility -> Enabled, performance -> Disabled) the higher-weighted dimension wins and
the conflict is surfaced as a trade-off note. Locked, unavailable, non-proposable, already-staged and
dismissed (unchanged evidence) settings are excluded.

Relevant Now uses a *hold rule*: the visible set is stored and only replaced on an explicit trigger
(first visit, simulated context event, user-confirmed refresh). Otherwise a new ranking only raises an
"update available" flag, so cards never reshuffle underneath the user.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..catalog.schema import DIMENSION_LABELS, Setting
from .db import dumps, loads, new_id, now_iso, write_tx
from .errors import Invalid
from .profile import ProfileService
from .store import Store
from .values import availability_problem, display_value, values_equal

MAX_RELEVANT_NOW = 3
BASIS_FACTOR = {"official": 1.0, "editorial": 0.8}


def _first_valid_target(setting: Setting, prefer: list[Any], current: Any) -> Any:
    for v in prefer:
        if not values_equal(v, current):
            return v
    return None


def rank_candidates(store: Store, profile: ProfileService, conn: sqlite3.Connection, game: str, *,
                    weights: Optional[dict[str, dict[str, Any]]] = None, limit: int = 10,
                    exclude_dismissed: bool = True, exclude_staged: bool = True) -> list[dict[str, Any]]:
    weights = weights if weights is not None else profile.dimension_weights(conn, game)
    positive = {d: w for d, w in weights.items() if w["weight"] > 0}
    if not positive:
        return []
    values = store.flat_values(conn, game)
    locked = set(store.locks(conn, game))
    hardware = store.hardware(conn)
    staged = {r["setting_id"] for r in conn.execute(
        "SELECT i.setting_id FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
        "WHERE p.game = ? AND p.status = 'pending' AND i.status = 'pending'", (game,))} if exclude_staged else set()
    signature = ProfileService.signature(weights)
    dismissed = {r["setting_id"] for r in conn.execute(
        "SELECT setting_id FROM dismissals WHERE game = ? AND signature = ?", (game, signature))} if exclude_dismissed else set()

    out: list[dict[str, Any]] = []
    for s in store.registry.settings(game):
        if not s.aiProposable or s.controlType in ("keybind", "preset") or not s.goalHints:
            continue
        if s.id in locked or s.id in staged or s.id in dismissed:
            continue
        if availability_problem(store.registry, s, values, hardware):
            continue
        current = values.get(s.id)
        # Best hint among positively weighted dimensions that the current value does not satisfy.
        scored: list[tuple[float, Any, Any]] = []
        satisfied_by_current: list[str] = []
        for h in s.goalHints:
            w = positive.get(h.dimension)
            if not w:
                continue
            if any(values_equal(current, v) for v in h.prefer):
                satisfied_by_current.append(h.dimension)
                continue
            target = _first_valid_target(s, h.prefer, current)
            if target is None:
                continue
            scored.append((w["weight"] * BASIS_FACTOR[h.basis], h, target))
        if not scored:
            continue
        scored.sort(key=lambda t: -t[0])
        best_score, best_hint, target = scored[0]
        # A higher-weighted dimension that the current value already satisfies blocks the change.
        if any(positive[d]["weight"] >= positive[best_hint.dimension]["weight"] for d in satisfied_by_current):
            continue
        conflicts = []
        for h in s.goalHints:
            if h.dimension == best_hint.dimension:
                continue
            w = weights.get(h.dimension, {}).get("weight", 0.0)
            prefers_target = any(values_equal(target, v) for v in h.prefer)
            if w > 0 and not prefers_target:
                conflicts.append(f"You also prioritize {DIMENSION_LABELS[h.dimension]}: {h.why}")
            if w < 0 and prefers_target:
                best_score += w  # user de-prioritized this dimension
        if best_score <= 0:
            continue
        reasons = weights[best_hint.dimension]["reasons"]
        out.append({
            "settingId": s.id,
            "label": s.exactLabel,
            "path": s.canonicalPath,
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
        })
    out.sort(key=lambda c: (-c["score"], c["order"]))
    return out[:limit]


class RelevantNowService:
    def __init__(self, store: Store, profile: ProfileService):
        self.store = store
        self.profile = profile

    def _card_state(self, conn: sqlite3.Connection, game: str, card: dict[str, Any]) -> dict[str, Any]:
        s = self.store.registry.setting(game, card["settingId"])
        state = card.get("state", "suggested")
        if s is None:
            return {**card, "state": "stale"}
        values = self.store.flat_values(conn, game)
        cur = values.get(s.id)
        if state not in ("dismissed",):
            if self.store.is_locked(conn, game, s.id):
                state = "locked"
            elif values_equal(cur, card["targetValue"]):
                state = "applied"
            elif conn.execute(
                "SELECT 1 FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id WHERE p.game = ? AND "
                "p.status = 'pending' AND i.status = 'pending' AND i.setting_id = ?", (game, s.id)).fetchone():
                state = "staged"
            elif not values_equal(cur, card["currentValue"]):
                state = "changed"
            else:
                state = "suggested"
        return {**card, "state": state, "liveValue": cur, "liveDisplay": display_value(s, cur)}

    def get(self, game: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            row = conn.execute("SELECT * FROM relevant_now WHERE game = ?", (game,)).fetchone()
            weights = self.profile.dimension_weights(conn, game)
            if row is None:
                return {"game": game, "items": [], "trigger": None, "createdAt": None, "updateAvailable": False,
                        "hasEvidence": bool(weights), "context": self.profile.active_context(conn, game)}
            items = [self._card_state(conn, game, c) for c in loads(row["items_json"], [])]
            fresh = rank_candidates(self.store, self.profile, conn, game, weights=weights, limit=MAX_RELEVANT_NOW)
            visible = [c["settingId"] for c in items if c["state"] in ("suggested", "changed")]
            fresh_ids = [c["settingId"] for c in fresh]
            update_available = bool(fresh_ids) and (
                ProfileService.signature(weights) != row["signature"] or
                (len(visible) < MAX_RELEVANT_NOW and any(f not in [c["settingId"] for c in items] for f in fresh_ids)))
            return {"game": game, "items": items, "trigger": row["trigger"], "createdAt": row["created_at"],
                    "updateAvailable": update_available, "hasEvidence": bool(weights),
                    "context": self.profile.active_context(conn, game)}
        finally:
            conn.close()

    def refresh(self, game: str, trigger: str) -> dict[str, Any]:
        if trigger not in ("first_visit", "context_event", "user_refresh", "preference_change"):
            raise Invalid("Unknown refresh trigger")
        conn = self.store.connect()
        try:
            with write_tx(conn):
                weights = self.profile.dimension_weights(conn, game)
                cands = rank_candidates(self.store, self.profile, conn, game, weights=weights, limit=MAX_RELEVANT_NOW)
                items = [{**c, "cardId": new_id("card"), "state": "suggested"} for c in cands]
                conn.execute(
                    "INSERT INTO relevant_now(game, items_json, signature, trigger, created_at) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(game) DO UPDATE SET items_json = excluded.items_json, signature = excluded.signature, "
                    "trigger = excluded.trigger, created_at = excluded.created_at",
                    (game, dumps(items), ProfileService.signature(weights), trigger, now_iso()))
        finally:
            conn.close()
        return self.get(game)

    def ensure_first_visit(self, game: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            exists = conn.execute("SELECT 1 FROM relevant_now WHERE game = ?", (game,)).fetchone()
        finally:
            conn.close()
        return self.get(game) if exists else self.refresh(game, "first_visit")

    def dismiss(self, game: str, setting_id: str, reason: Optional[str]) -> dict[str, Any]:
        s = self.store.require_setting(game, setting_id)
        conn = self.store.connect()
        try:
            with write_tx(conn):
                weights = self.profile.dimension_weights(conn, game)
                conn.execute(
                    "INSERT INTO dismissals(id, game, setting_id, reason, signature, session_id, created_at) VALUES (?,?,?,?,?,?,?)",
                    (new_id("dis"), game, setting_id, reason, ProfileService.signature(weights),
                     self.store.session(conn)["sessionId"], now_iso()))
                row = conn.execute("SELECT items_json FROM relevant_now WHERE game = ?", (game,)).fetchone()
                if row:
                    items = loads(row["items_json"], [])
                    for c in items:
                        if c["settingId"] == setting_id:
                            c["state"] = "dismissed"
                            c["dismissReason"] = reason
                    conn.execute("UPDATE relevant_now SET items_json = ? WHERE game = ?", (dumps(items), game))
                dims = [h.dimension for h in s.goalHints if h.dimension in weights]
                for d in dims or [None]:
                    self.profile.add_evidence(conn, kind="dismissed", dimension=d, game=game, setting_id=setting_id,
                                              detail=f"Dismissed suggestion for {s.exactLabel}" + (f" ({reason})" if reason else ""))
        finally:
            conn.close()
        return self.get(game)
