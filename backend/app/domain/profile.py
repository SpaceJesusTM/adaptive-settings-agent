"""User profile: durable preferences vs transient session goals, evidence, and simulated context.

* Durable preferences are abstract (e.g. "prioritize low input latency") and shared across games. They are
  only created by an explicit user action (or a seeded scenario), never silently by the AI.
* Session goals are transient, game-specific statements of what the user wants right now.
* Evidence records what happened (applied / rejected / dismissed suggestions, chat statements) with its
  source, so the UI can show *why* a preference or recommendation exists.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any, Optional

from ..catalog.schema import DIMENSION_LABELS
from .db import dumps, loads, new_id, now_iso, write_tx
from .errors import Invalid, NotFound
from .store import Store

DIMENSIONS = list(DIMENSION_LABELS)

PERSONAL_FACT_TYPES: dict[str, dict[str, Any]] = {
    "mouse_sensitivity": {
        "label": "Mouse sensitivity",
        "description": "Your preferred hipfire aiming sensitivity in a source game (used only with explicit conversion caveats, never auto-applied).",
        "placeholder": "e.g. 0.35",
    },
    "push_to_talk_key": {
        "label": "Push-to-talk key",
        "description": "Your usual voice chat keybinding (used to point out analogous voice keys across games, never copied automatically).",
        "placeholder": "e.g. V",
    },
    "voice_activation": {
        "label": "Voice chat mode",
        "description": "Whether you prefer Push-to-Talk, Open Mic, or team/party voice conventions.",
        "placeholder": "e.g. Push-to-Talk",
    },
    "ping_key": {
        "label": "Ping / callout key",
        "description": "Your preferred tactical ping keybinding.",
        "placeholder": "e.g. Z",
    },
    "crouch_walk_convention": {
        "label": "Movement / crouch-walk habit",
        "description": "Hold vs Toggle crouch/walk preference or Shift/Ctrl convention.",
        "placeholder": "e.g. Hold Walk / Hold Duck",
    },
    "crosshair_style": {
        "label": "Crosshair style",
        "description": "High-level visual style (color, center dot, outlines, static vs dynamic) — never assumed pixel-identical across engines.",
        "placeholder": "e.g. Cyan static with outlines",
    },
    "utility_key_habit": {
        "label": "Ability / utility key habit",
        "description": "How you organize utility/grenade binds across hands.",
        "placeholder": "e.g. Q / E / C for core utility",
    },
}

CONFLICT_PAIRS: dict[str, tuple[str, ...]] = {
    "performance": ("visual_quality",),
    "input_latency": ("visual_quality",),
    "visual_quality": ("performance", "input_latency", "focus"),
    "visibility": ("visual_quality",),
    "focus": ("visual_quality",),
}

CONTEXT_EVENTS: dict[str, dict[str, Any]] = {
    "frame_drops": {"label": "Frame-rate dips were reported in your last match", "dimensions": ["performance"]},
    "ranked_session": {"label": "You are starting a competitive (ranked) session", "dimensions": ["input_latency", "visibility"]},
    "footsteps_hard_to_hear": {"label": "You reported trouble hearing footsteps", "dimensions": ["audio_awareness"]},
    "unstable_connection": {"label": "Packet loss was detected on your connection", "dimensions": ["network_stability"]},
}

WEIGHT_SESSION_GOAL = 1.0
WEIGHT_SESSION_PREF = 0.9
WEIGHT_DURABLE_PREF = 0.8
WEIGHT_CONTEXT = 0.6


def game_name(game: Optional[str]) -> str:
    return {"valorant": "VALORANT", "cs2": "CS2"}.get(game or "", game or "")


class ProfileService:
    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------------ preferences
    @staticmethod
    def _source_category(kind: str, detail: Optional[str] = None) -> str:
        if detail and "(seeded history)" in detail.lower():
            return "scenario_seed"
        return {
            "preference_set": "explicit_statement",
            "personal_fact_set": "explicit_statement",
            "applied": "ai_applied",
            "manual_change": "manual_change",
            "rejected": "rejected_or_dismissed",
            "dismissed": "rejected_or_dismissed",
            "checked": "user_checked",
        }.get(kind, "system_observation")

    def preferences(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        sess = self.store.session(conn)
        rows = conn.execute(
            "SELECT * FROM preferences WHERE active = 1 AND (scope = 'durable' OR session_id = ?) ORDER BY created_at",
            (sess["sessionId"],)).fetchall()
        out = []
        for r in rows:
            pref_id = r["id"]
            ev = conn.execute(
                "SELECT kind, game, setting_id, detail, created_at, preference_id FROM evidence "
                "WHERE preference_id = ? ORDER BY created_at DESC LIMIT 6",
                (pref_id,),
            ).fetchall()
            if not ev and r["source"] == "seed":
                # Seeded scenario preferences may reference matching scenario evidence rows without preference_id
                ev = conn.execute(
                    "SELECT kind, game, setting_id, detail, created_at, preference_id FROM evidence "
                    "WHERE preference_id IS NULL AND dimension = ? ORDER BY created_at DESC LIMIT 4",
                    (r["dimension"],),
                ).fetchall()
            ev_list = [
                {
                    "kind": e["kind"],
                    "game": e["game"],
                    "setting_id": e["setting_id"],
                    "detail": e["detail"],
                    "created_at": e["created_at"],
                    "sourceCategory": self._source_category(e["kind"], e["detail"]),
                }
                for e in ev
            ]
            out.append({
                "id": pref_id,
                "dimension": r["dimension"],
                "dimensionLabel": DIMENSION_LABELS.get(r["dimension"], r["dimension"]),
                "direction": r["direction"],
                "scope": r["scope"],
                "game": r["game"],
                "originGame": r["origin_game"],
                "source": r["source"],
                "note": r["note"],
                "createdAt": r["created_at"],
                "evidence": ev_list,
            })
        return out

    def add_preference(self, *, dimension: str, direction: str, scope: str, source: str,
                       game: Optional[str], origin_game: Optional[str], note: Optional[str]) -> dict[str, Any]:
        if dimension not in DIMENSIONS:
            raise Invalid(f"Unknown preference dimension '{dimension}'")
        if direction not in ("prioritize", "deprioritize"):
            raise Invalid("direction must be 'prioritize' or 'deprioritize'")
        if scope not in ("durable", "session"):
            raise Invalid("scope must be 'durable' or 'session'")
        if source not in ("user_explicit", "chat_confirmed", "chat_explicit", "seed"):
            raise Invalid("Preferences can only be created by an explicit user action.")
        conn = self.store.connect()
        try:
            with write_tx(conn):
                pid = self.add_preference_tx(
                    conn,
                    dimension=dimension,
                    direction=direction,
                    scope=scope,
                    source=source,
                    game=game,
                    origin_game=origin_game,
                    note=note,
                )
            return {"id": pid}
        finally:
            conn.close()

    def add_preference_tx(
        self,
        conn: sqlite3.Connection,
        *,
        dimension: str,
        direction: str,
        scope: str,
        source: str,
        game: Optional[str],
        origin_game: Optional[str],
        note: Optional[str],
    ) -> str:
        """Persist a confirmed preference inside an active write transaction."""
        sess = self.store.session(conn)
        conn.execute(
            "UPDATE preferences SET active = 0, updated_at = ? WHERE dimension = ? AND scope = ? AND active = 1 "
            "AND (scope = 'durable' OR session_id = ?)",
            (now_iso(), dimension, scope, sess["sessionId"]),
        )
        pid = new_id("pref")
        ts = now_iso()
        conn.execute(
            "INSERT INTO preferences(id, dimension, direction, scope, session_id, game, origin_game, source, note, active, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,1,?,?)",
            (pid, dimension, direction, scope, sess["sessionId"] if scope == "session" else None, game,
             origin_game or game, source, note, ts, ts),
        )
        self.add_evidence(
            conn,
            kind="preference_set",
            dimension=dimension,
            game=game,
            preference_id=pid,
            detail=f"{'Prioritize' if direction == 'prioritize' else 'De-prioritize'} "
                   f"{DIMENSION_LABELS[dimension]} ({'lasting' if scope == 'durable' else 'this session only'})"
                   + (f": {note}" if note else ""),
        )
        return pid

    def remove_preference(self, pref_id: str) -> None:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                row = conn.execute("SELECT * FROM preferences WHERE id = ?", (pref_id,)).fetchone()
                if row is None:
                    raise NotFound("Unknown preference")
                conn.execute("UPDATE preferences SET active = 0, updated_at = ? WHERE id = ?", (now_iso(), pref_id))
                self.add_evidence(conn, kind="preference_removed", dimension=row["dimension"], game=row["game"],
                                  preference_id=pref_id,
                                  detail=f"Removed preference for {DIMENSION_LABELS.get(row['dimension'], row['dimension'])}")
        finally:
            conn.close()

    def add_evidence(self, conn: sqlite3.Connection, *, kind: str, dimension: Optional[str] = None,
                     game: Optional[str] = None, setting_id: Optional[str] = None, proposal_id: Optional[str] = None,
                     preference_id: Optional[str] = None, detail: Optional[str] = None) -> None:
        sess = self.store.session(conn)
        conn.execute(
            "INSERT INTO evidence(id, kind, dimension, game, setting_id, proposal_id, preference_id, detail, session_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_id("ev"), kind, dimension, game, setting_id, proposal_id, preference_id, detail, sess["sessionId"], now_iso()))

    def snapshot_context(self, conn: sqlite3.Connection, game: str) -> dict[str, Any]:
        """Lightweight snapshot of active goals/priorities used to detect semantically stale proposals later."""
        goals = self.session_goals(conn, game)
        prefs = self.preferences(conn)
        ctx = self.active_context(conn, game)
        return {
            "goalText": goals[0]["text"] if goals else None,
            "goalDimensions": list(goals[0]["dimensions"]) if goals else [],
            "preferences": [
                {"id": p["id"], "dimension": p["dimension"], "direction": p["direction"], "scope": p["scope"]}
                for p in prefs
            ],
            "contextEventType": ctx["eventType"] if ctx else None,
        }

    def evidence(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
        rows = conn.execute("SELECT * FROM evidence ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ session goals
    def session_goals(self, conn: sqlite3.Connection, game: str) -> list[dict[str, Any]]:
        sess = self.store.session(conn)
        rows = conn.execute(
            "SELECT * FROM session_goals WHERE active = 1 AND session_id = ? AND game = ? ORDER BY created_at",
            (sess["sessionId"], game)).fetchall()
        return [{"id": r["id"], "text": r["text"], "dimensions": loads(r["dimensions_json"], []), "source": r["source"],
                 "createdAt": r["created_at"]} for r in rows]

    def set_session_goal(self, conn: sqlite3.Connection, game: str, text: str, dimensions: list[str], source: str) -> Optional[str]:
        dims = [d for d in dict.fromkeys(dimensions) if d in DIMENSIONS]
        if not dims:
            return None
        sess = self.store.session(conn)
        # The newest explicit goal replaces earlier ones for this game/session (a "goal change").
        conn.execute("UPDATE session_goals SET active = 0 WHERE session_id = ? AND game = ? AND active = 1",
                     (sess["sessionId"], game))
        gid = new_id("goal")
        conn.execute(
            "INSERT INTO session_goals(id, session_id, game, text, dimensions_json, source, active, created_at) VALUES (?,?,?,?,?,?,1,?)",
            (gid, sess["sessionId"], game, text[:200], dumps(dims), source, now_iso()))
        return gid

    def clear_session_goals(self, game: str) -> None:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                sess = self.store.session(conn)
                conn.execute("UPDATE session_goals SET active = 0 WHERE session_id = ? AND game = ?", (sess["sessionId"], game))
        finally:
            conn.close()

    # ------------------------------------------------------------------ simulated context
    def active_context(self, conn: sqlite3.Connection, game: str) -> Optional[dict[str, Any]]:
        sess = self.store.session(conn)
        row = conn.execute(
            "SELECT * FROM context_events WHERE game = ? AND session_id = ? AND active = 1 ORDER BY created_at DESC LIMIT 1",
            (game, sess["sessionId"])).fetchone()
        if row is None:
            return None
        spec = CONTEXT_EVENTS.get(row["event_type"], {})
        return {"id": row["id"], "eventType": row["event_type"], "label": spec.get("label", row["event_type"]),
                "dimensions": spec.get("dimensions", []), "createdAt": row["created_at"], "simulated": True}

    def set_context(self, conn: sqlite3.Connection, game: str, event_type: Optional[str]) -> None:
        sess = self.store.session(conn)
        conn.execute("UPDATE context_events SET active = 0 WHERE game = ? AND session_id = ?", (game, sess["sessionId"]))
        if event_type:
            if event_type not in CONTEXT_EVENTS:
                raise Invalid(f"Unknown simulated event '{event_type}'")
            conn.execute("INSERT INTO context_events(id, game, event_type, session_id, active, created_at) VALUES (?,?,?,?,1,?)",
                         (new_id("ctx"), game, event_type, sess["sessionId"], now_iso()))

    # ------------------------------------------------------------------ weights
    def dimension_weights(self, conn: sqlite3.Connection, game: str) -> dict[str, dict[str, Any]]:
        weights: dict[str, dict[str, Any]] = {}

        def add(dim: str, w: float, reason: dict[str, Any]) -> None:
            entry = weights.setdefault(dim, {"weight": 0.0, "reasons": []})
            entry["weight"] = round(entry["weight"] + w, 3)
            entry["reasons"].append(reason)

        for g in self.session_goals(conn, game):
            for d in g["dimensions"]:
                add(d, WEIGHT_SESSION_GOAL, {"kind": "session_goal", "text": f"your current goal \"{g['text']}\" (this session)"})
        for p in self.preferences(conn):
            sign = 1 if p["direction"] == "prioritize" else -1
            if p["scope"] == "session":
                add(p["dimension"], sign * WEIGHT_SESSION_PREF,
                    {"kind": "session_preference", "text": f"your preference for {p['dimensionLabel']} (this session)"})
            else:
                origin = p.get("originGame")
                where = f" in {game_name(origin)}" if origin and origin != game else ""
                add(p["dimension"], sign * WEIGHT_DURABLE_PREF,
                    {"kind": "durable_preference", "originGame": origin, "crossGame": bool(origin and origin != game),
                     "text": f"your saved preference for {p['dimensionLabel']}{where}"})
        ctx = self.active_context(conn, game)
        if ctx:
            for d in ctx["dimensions"]:
                add(d, WEIGHT_CONTEXT, {"kind": "context", "text": f"simulated context: {ctx['label'].lower()}"})
        return weights

    @staticmethod
    def signature(weights: dict[str, dict[str, Any]]) -> str:
        items = sorted((d, round(v["weight"], 2)) for d, v in weights.items() if abs(v["weight"]) > 1e-9)
        return hashlib.sha1(repr(items).encode()).hexdigest()[:12]

    # ------------------------------------------------------------------ personal setup facts
    def personal_facts(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM personal_setup_facts WHERE active = 1 ORDER BY created_at"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "factKey": r["fact_key"],
                "label": r["label"],
                "valueText": r["value_text"],
                "originGame": r["origin_game"],
                "sourceSettingId": r["source_setting_id"],
                "source": r["source"],
                "note": r["note"],
                "createdAt": r["created_at"],
            }
            for r in rows
        ]

    def add_personal_fact_tx(
        self,
        conn: sqlite3.Connection,
        *,
        fact_key: str,
        value_text: str,
        origin_game: Optional[str],
        source_setting_id: Optional[str],
        source: str,
        note: Optional[str] = None,
    ) -> str:
        spec = PERSONAL_FACT_TYPES[fact_key]
        clean_val = (value_text or "").strip()
        ts = now_iso()
        conn.execute(
            "UPDATE personal_setup_facts SET active = 0, updated_at = ? "
            "WHERE fact_key = ? AND COALESCE(origin_game, '') = ? AND active = 1",
            (ts, fact_key, origin_game or ""),
        )
        fid = new_id("fact")
        conn.execute(
            "INSERT INTO personal_setup_facts(id, fact_key, label, value_text, origin_game, "
            "source_setting_id, source, note, active, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (fid, fact_key, spec["label"], clean_val, origin_game, source_setting_id, source, note, ts, ts),
        )
        self.add_evidence(
            conn,
            kind="personal_fact_set",
            game=origin_game,
            setting_id=source_setting_id,
            detail=f"Confirmed {spec['label']}: {clean_val}"
            + (f" ({game_name(origin_game)})" if origin_game else ""),
        )
        return fid

    def add_personal_fact(
        self,
        *,
        fact_key: str,
        value_text: str,
        origin_game: Optional[str],
        source_setting_id: Optional[str],
        source: str,
        note: Optional[str] = None,
    ) -> dict[str, Any]:
        if fact_key not in PERSONAL_FACT_TYPES:
            raise Invalid(f"Unknown personal setup preference type '{fact_key}'")
        if source not in ("user_explicit", "chat_confirmed", "chat_explicit", "seed"):
            raise Invalid("Personal setup facts require explicit user confirmation.")
        clean_val = (value_text or "").strip()
        if not clean_val or len(clean_val) > 120:
            raise Invalid("Value must be 1 to 120 characters.")
        conn = self.store.connect()
        try:
            with write_tx(conn):
                fid = self.add_personal_fact_tx(
                    conn,
                    fact_key=fact_key,
                    value_text=clean_val,
                    origin_game=origin_game,
                    source_setting_id=source_setting_id,
                    source=source,
                    note=note,
                )
            return {"id": fid}
        finally:
            conn.close()

    def remove_personal_fact(self, fact_id: str) -> None:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                row = conn.execute("SELECT * FROM personal_setup_facts WHERE id = ?", (fact_id,)).fetchone()
                if row is None:
                    raise NotFound("Unknown personal setup preference")
                conn.execute(
                    "UPDATE personal_setup_facts SET active = 0, updated_at = ? WHERE id = ?",
                    (now_iso(), fact_id),
                )
                self.add_evidence(
                    conn,
                    kind="personal_fact_removed",
                    game=row["origin_game"],
                    setting_id=row["source_setting_id"],
                    detail=f"Removed personal preference for {row['label']}",
                )
        finally:
            conn.close()

    # ------------------------------------------------------------------ conflicts & onboarding state
    def goal_preference_conflicts(self, conn: sqlite3.Connection, game: str) -> list[dict[str, Any]]:
        goals = self.session_goals(conn, game)
        if not goals:
            return []
        prefs = self.preferences(conn)
        conflicts: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for g in goals:
            g_dims = set(g["dimensions"])
            for gd in g["dimensions"]:
                opposing = CONFLICT_PAIRS.get(gd, ())
                for p in prefs:
                    key = (gd, p["id"])
                    if key in seen:
                        continue
                    if p["dimension"] == gd and p["direction"] == "deprioritize":
                        seen.add(key)
                        conflicts.append({
                            "goalDimension": gd,
                            "goalDimensionLabel": DIMENSION_LABELS.get(gd, gd),
                            "preferenceId": p["id"],
                            "preferenceLabel": p["dimensionLabel"],
                            "preferenceDirection": p["direction"],
                            "scope": p["scope"],
                            "explanation": (
                                f"Your current goal asks for {DIMENSION_LABELS.get(gd, gd)}, while your saved "
                                f"preference de-prioritizes it. Your current goal leads this session's guidance."
                            ),
                        })
                    elif p["dimension"] in opposing and p["direction"] == "prioritize" and p["dimension"] not in g_dims:
                        seen.add(key)
                        conflicts.append({
                            "goalDimension": gd,
                            "goalDimensionLabel": DIMENSION_LABELS.get(gd, gd),
                            "preferenceId": p["id"],
                            "preferenceLabel": p["dimensionLabel"],
                            "preferenceDirection": p["direction"],
                            "scope": p["scope"],
                            "explanation": (
                                f"Your current goal ({DIMENSION_LABELS.get(gd, gd)}) can trade off against your "
                                f"saved priority ({p['dimensionLabel']}). Your current goal leads here while "
                                f"trade-offs stay visible."
                            ),
                        })
        return conflicts

    def get_onboarding(self, conn: sqlite3.Connection, game: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM onboarding_state WHERE game = ?", (game,)).fetchone()
        if row is None:
            return {
                "game": game,
                "status": None,
                "completedChecks": [],
                "dismissedChecks": [],
                "firstVisitedAt": None,
            }
        return {
            "game": game,
            "status": row["status"],
            "completedChecks": loads(row["completed_checks_json"], []),
            "dismissedChecks": loads(row["dismissed_checks_json"], []),
            "firstVisitedAt": row["first_visited_at"],
        }

    def ensure_onboarding_tx(self, conn: sqlite3.Connection, game: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM onboarding_state WHERE game = ?", (game,)).fetchone()
        if row is None:
            ts = now_iso()
            conn.execute(
                "INSERT INTO onboarding_state(game, first_visited_at, status, completed_checks_json, "
                "dismissed_checks_json, updated_at) VALUES (?,?,?,?,?,?)",
                (game, ts, "active", "[]", "[]", ts),
            )
        return self.get_onboarding(conn, game)

    def mark_onboarding_check(self, conn: sqlite3.Connection, game: str, check_id: str, action: str = "complete") -> dict[str, Any]:
        state = self.ensure_onboarding_tx(conn, game)
        completed = list(dict.fromkeys(state["completedChecks"]))
        dismissed = list(dict.fromkeys(state["dismissedChecks"]))
        if action == "complete":
            if check_id not in completed:
                completed.append(check_id)
        else:
            if check_id not in dismissed:
                dismissed.append(check_id)
        conn.execute(
            "UPDATE onboarding_state SET completed_checks_json = ?, dismissed_checks_json = ?, updated_at = ? WHERE game = ?",
            (dumps(completed), dumps(dismissed), now_iso(), game),
        )
        return self.get_onboarding(conn, game)

    def set_onboarding_status_tx(self, conn: sqlite3.Connection, game: str, status: str, *, clear_dismissed: bool = False) -> dict[str, Any]:
        self.ensure_onboarding_tx(conn, game)
        if clear_dismissed:
            conn.execute(
                "UPDATE onboarding_state SET status = ?, dismissed_checks_json = '[]', updated_at = ? WHERE game = ?",
                (status, now_iso(), game),
            )
        else:
            conn.execute(
                "UPDATE onboarding_state SET status = ?, updated_at = ? WHERE game = ?",
                (status, now_iso(), game),
            )
        return self.get_onboarding(conn, game)
