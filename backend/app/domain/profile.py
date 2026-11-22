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
    def preferences(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        sess = self.store.session(conn)
        rows = conn.execute(
            "SELECT * FROM preferences WHERE active = 1 AND (scope = 'durable' OR session_id = ?) ORDER BY created_at",
            (sess["sessionId"],)).fetchall()
        out = []
        for r in rows:
            ev = conn.execute(
                "SELECT kind, game, setting_id, detail, created_at FROM evidence WHERE dimension = ? ORDER BY created_at DESC LIMIT 6",
                (r["dimension"],)).fetchall()
            out.append({
                "id": r["id"], "dimension": r["dimension"], "dimensionLabel": DIMENSION_LABELS.get(r["dimension"], r["dimension"]),
                "direction": r["direction"], "scope": r["scope"], "game": r["game"], "originGame": r["origin_game"],
                "source": r["source"], "note": r["note"], "createdAt": r["created_at"],
                "evidence": [dict(e) for e in ev],
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
        if source not in ("user_explicit", "chat_confirmed", "seed"):
            raise Invalid("Preferences can only be created by an explicit user action.")
        conn = self.store.connect()
        try:
            with write_tx(conn):
                sess = self.store.session(conn)
                # One active preference per (dimension, scope): a new statement replaces the old one.
                conn.execute(
                    "UPDATE preferences SET active = 0, updated_at = ? WHERE dimension = ? AND scope = ? AND active = 1 "
                    "AND (scope = 'durable' OR session_id = ?)", (now_iso(), dimension, scope, sess["sessionId"]))
                pid = new_id("pref")
                ts = now_iso()
                conn.execute(
                    "INSERT INTO preferences(id, dimension, direction, scope, session_id, game, origin_game, source, note, active, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,1,?,?)",
                    (pid, dimension, direction, scope, sess["sessionId"] if scope == "session" else None, game,
                     origin_game or game, source, note, ts, ts))
                self.add_evidence(conn, kind="preference_set", dimension=dimension, game=game,
                                  detail=f"{'Prioritize' if direction == 'prioritize' else 'De-prioritize'} "
                                         f"{DIMENSION_LABELS[dimension]} ({'lasting' if scope == 'durable' else 'this session only'})"
                                         + (f": {note}" if note else ""))
            return {"id": pid}
        finally:
            conn.close()

    def remove_preference(self, pref_id: str) -> None:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                row = conn.execute("SELECT * FROM preferences WHERE id = ?", (pref_id,)).fetchone()
                if row is None:
                    raise NotFound("Unknown preference")
                conn.execute("UPDATE preferences SET active = 0, updated_at = ? WHERE id = ?", (now_iso(), pref_id))
                self.add_evidence(conn, kind="preference_removed", dimension=row["dimension"], game=row["game"],
                                  detail=f"Removed preference for {DIMENSION_LABELS.get(row['dimension'], row['dimension'])}")
        finally:
            conn.close()

    def add_evidence(self, conn: sqlite3.Connection, *, kind: str, dimension: Optional[str] = None,
                     game: Optional[str] = None, setting_id: Optional[str] = None, proposal_id: Optional[str] = None,
                     detail: Optional[str] = None) -> None:
        sess = self.store.session(conn)
        conn.execute(
            "INSERT INTO evidence(id, kind, dimension, game, setting_id, proposal_id, detail, session_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id("ev"), kind, dimension, game, setting_id, proposal_id, detail, sess["sessionId"], now_iso()))

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
