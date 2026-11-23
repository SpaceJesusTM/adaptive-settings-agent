"""Authoritative settings store: values, revisions, history, undo, pins, locks, session state.

`_apply_tx` is the ONLY function that writes setting values. Manual edits, approved proposals, presets,
undo and scenario resets all call it. AI code never touches it directly: AI output can only become a
proposal, and a proposal only reaches `_apply_tx` through an explicit user "apply" request.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from ..catalog.loader import CatalogRegistry
from ..catalog.schema import Setting
from . import db
from .db import dumps, loads, new_id, now_iso, write_tx
from .errors import Conflict, Invalid, NotFound
from .values import ValueError_, availability_problem, display_value, normalize_value, values_equal

DEFAULT_HARDWARE = {
    "label": "Simulated gaming PC",
    "gpuVendor": "NVIDIA",
    "gpu": "Simulated NVIDIA GPU (8 GB VRAM)",
    "cpuCores": 12,
    "ramGB": 16,
    "vramGB": 8,
    "displayRefreshHz": 144,
    "gsyncDisplay": False,
}

SOURCE_LABELS = {
    "manual": "Manual change",
    "manual_batch": "Manual change (applied together)",
    "ai_applied": "AI proposed · user applied",
    "fallback_applied": "Fallback suggestion · user applied",
    "rule_applied": "Rule-based suggestion · user applied",
    "history_applied": "Restaged from history · user applied",
    "undo": "Undo",
    "preset": "Video preset",
}


@dataclass
class Change:
    setting_id: str
    value: Any
    expected_revision: Optional[int] = None


class Store:
    def __init__(self, db_path: Path, registry: CatalogRegistry):
        self.db_path = db_path
        self.registry = registry
        conn = self.connect()
        try:
            db.bootstrap(conn)
        finally:
            conn.close()

    # ------------------------------------------------------------------ connections
    def connect(self) -> sqlite3.Connection:
        return db.connect(self.db_path)

    # ------------------------------------------------------------------ session / kv
    def kv_get(self, conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
        row = conn.execute("SELECT value_json FROM kv WHERE key = ?", (key,)).fetchone()
        return loads(row["value_json"]) if row else default

    def kv_set(self, conn: sqlite3.Connection, key: str, value: Any) -> None:
        conn.execute(
            "INSERT INTO kv(key, value_json) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
            (key, dumps(value)),
        )

    def session(self, conn: sqlite3.Connection) -> dict[str, Any]:
        s = self.kv_get(conn, "session")
        if s is None:
            s = {
                "sessionId": new_id("ses"),
                "condition": "baseline",
                "selectedGame": "valorant",
                "adaptationEnabled": True,
                "aiMode": "local",
                "scenario": None,
                "hardware": dict(DEFAULT_HARDWARE),
                "startedAt": now_iso(),
            }
            if conn.in_transaction:
                self.kv_set(conn, "session", s)
            else:
                with write_tx(conn):
                    self.kv_set(conn, "session", s)
        return s

    def update_session(self, conn: sqlite3.Connection, **changes: Any) -> dict[str, Any]:
        s = self.session(conn)
        allowed = {"condition", "selectedGame", "adaptationEnabled", "aiMode"}
        for k, v in changes.items():
            if v is None:
                continue
            if k not in allowed:
                raise Invalid(f"Unknown session field {k}")
            if k == "condition" and v not in ("baseline", "adaptive"):
                raise Invalid("condition must be 'baseline' or 'adaptive'")
            if k == "selectedGame" and v not in self.registry.games:
                raise Invalid(f"Unknown game {v}")
            if k == "aiMode" and v not in ("local", "fallback"):
                raise Invalid("aiMode must be 'local' or 'fallback'")
            if k == "adaptationEnabled":
                v = bool(v)
            s[k] = v
        if conn.in_transaction:
            self.kv_set(conn, "session", s)
        else:
            with write_tx(conn):
                self.kv_set(conn, "session", s)
        return s

    def hardware(self, conn: sqlite3.Connection) -> dict[str, Any]:
        return self.session(conn).get("hardware") or dict(DEFAULT_HARDWARE)

    # ------------------------------------------------------------------ reads
    def require_game(self, game: str) -> None:
        if game not in self.registry.games:
            raise NotFound(f"Unknown game '{game}'")

    def require_setting(self, game: str, setting_id: str) -> Setting:
        self.require_game(game)
        s = self.registry.setting(game, setting_id)
        if s is None:
            other = self.registry.find_any_game(setting_id)
            if other is not None:
                raise Invalid(f"'{setting_id}' belongs to {other.game.upper()}, not {game.upper()}", code="wrong_game")
            raise Invalid(f"Unknown setting id '{setting_id}' for {game.upper()}", code="unknown_setting")
        return s

    def values(self, conn: sqlite3.Connection, game: str) -> dict[str, dict[str, Any]]:
        rows = conn.execute("SELECT setting_id, value_json, revision FROM setting_values WHERE game = ?", (game,)).fetchall()
        out = {r["setting_id"]: {"value": loads(r["value_json"]), "revision": r["revision"]} for r in rows}
        for s in self.registry.settings(game):
            if s.controlType == "preset":
                out[s.id] = {"value": self.derive_preset(s, out), "revision": 0, "derived": True}
        return out

    def flat_values(self, conn: sqlite3.Connection, game: str) -> dict[str, Any]:
        return {k: v["value"] for k, v in self.values(conn, game).items()}

    def game_revision(self, conn: sqlite3.Connection, game: str) -> int:
        row = conn.execute("SELECT revision FROM game_state WHERE game = ?", (game,)).fetchone()
        return int(row["revision"]) if row else 0

    def derive_preset(self, preset: Setting, values: dict[str, dict[str, Any]]) -> str:
        assert preset.preset is not None
        for pval, mapping in preset.preset.values.items():
            ok = True
            for member, mv in mapping.items():
                ms = self.registry.by_key(preset.game, member)
                cur = values.get(ms.id, {}).get("value") if ms else None
                if cur is None or not values_equal(cur, mv):
                    ok = False
                    break
            if ok:
                return pval
        return "custom"

    def locks(self, conn: sqlite3.Connection, game: str) -> list[str]:
        return [r["setting_id"] for r in conn.execute("SELECT setting_id FROM locks WHERE game = ? ORDER BY created_at", (game,))]

    def pins(self, conn: sqlite3.Connection, game: str) -> list[str]:
        return [r["setting_id"] for r in conn.execute("SELECT setting_id FROM pins WHERE game = ? ORDER BY created_at", (game,))]

    def is_locked(self, conn: sqlite3.Connection, game: str, setting_id: str) -> bool:
        return conn.execute("SELECT 1 FROM locks WHERE game = ? AND setting_id = ?", (game, setting_id)).fetchone() is not None

    # ------------------------------------------------------------------ the single write path
    def _expand(self, game: str, changes: Iterable[Change]) -> list[tuple[Setting, Any, Optional[int], Optional[str]]]:
        """Resolve settings; expand preset selections into member changes."""
        out: list[tuple[Setting, Any, Optional[int], Optional[str]]] = []
        for ch in changes:
            s = self.require_setting(game, ch.setting_id)
            if s.controlType == "preset":
                try:
                    pval = normalize_value(s, ch.value, strict=True)
                except ValueError_ as exc:
                    raise Invalid(str(exc), code="invalid_value", details={"settingId": s.id}) from exc
                if pval == "custom" or s.preset is None or pval not in s.preset.values:
                    raise Invalid("Choose Low, Medium, High or Very High; 'Custom' is shown automatically.",
                                  code="invalid_value", details={"settingId": s.id})
                for member, mv in s.preset.values[pval].items():
                    ms = self.registry.by_key(game, member)
                    assert ms is not None
                    out.append((ms, mv, None, s.id))
            else:
                out.append((s, ch.value, ch.expected_revision, None))
        return out

    def _apply_tx(
        self,
        conn: sqlite3.Connection,
        game: str,
        changes: list[Change],
        *,
        source: str,
        label: Optional[str],
        enforce_locks: bool,
        strict: bool,
        check_availability: bool = True,
        proposal_id: Optional[str] = None,
        client_request_id: Optional[str] = None,
        undoes_batch_id: Optional[str] = None,
        sync_crosshair_profile: bool = True,
    ) -> dict[str, Any]:
        """Validate everything first, then write everything. Caller must hold a write transaction."""
        if client_request_id:
            row = conn.execute("SELECT id FROM change_batches WHERE client_request_id = ?", (client_request_id,)).fetchone()
            if row:
                summary = self.batch_summary(conn, row["id"])
                summary["idempotentReplay"] = True
                return summary

        current = self.values(conn, game)
        expanded = self._expand(game, changes)
        seen: set[str] = set()
        problems: list[dict[str, Any]] = []
        planned: list[tuple[Setting, Any]] = []
        for s, raw, expected_rev, _via_preset in expanded:
            if s.id in seen:
                problems.append({"settingId": s.id, "reason": "Setting appears twice in one change set."})
                continue
            seen.add(s.id)
            try:
                value = normalize_value(s, raw, strict=strict)
            except ValueError_ as exc:
                problems.append({"settingId": s.id, "label": s.exactLabel, "reason": str(exc), "kind": "invalid_value"})
                continue
            cur = current.get(s.id, {"value": None, "revision": 0})
            if expected_rev is not None and int(expected_rev) != int(cur["revision"]):
                problems.append({"settingId": s.id, "label": s.exactLabel, "kind": "stale_revision",
                                 "reason": f"{s.exactLabel} changed since this edit was prepared (now {display_value(s, cur['value'])}).",
                                 "currentValue": cur["value"], "currentRevision": cur["revision"]})
                continue
            if enforce_locks and self.is_locked(conn, game, s.id):
                problems.append({"settingId": s.id, "label": s.exactLabel, "kind": "locked",
                                 "reason": f"{s.exactLabel} is locked from AI changes. Unlock it or leave it out."})
                continue
            planned.append((s, value))

        if check_availability and not problems:
            hypothetical = {k: v["value"] for k, v in current.items()}
            for s, value in planned:
                hypothetical[s.id] = value
            hw = self.hardware(conn)
            for s, value in planned:
                if values_equal(current.get(s.id, {}).get("value"), value):
                    continue
                reason = availability_problem(self.registry, s, hypothetical, hw)
                if reason:
                    problems.append({"settingId": s.id, "label": s.exactLabel, "kind": "unavailable", "reason": reason})

        if problems:
            kinds = {p.get("kind") for p in problems}
            msg = "; ".join(p["reason"] for p in problems)
            if kinds & {"stale_revision", "locked"}:
                raise Conflict(f"No changes were applied. {msg}", code="conflict", details={"problems": problems})
            raise Invalid(f"No changes were applied. {msg}", code="invalid_change", details={"problems": problems})

        effective = [(s, v) for s, v in planned if not values_equal(current.get(s.id, {}).get("value"), v)]
        if not effective:
            return {"batchId": None, "game": game, "events": [], "gameRevision": self.game_revision(conn, game),
                    "values": {}, "noop": True}

        ts = now_iso()
        batch_id = new_id("bat")
        sess = self.session(conn)
        conn.execute(
            "INSERT INTO change_batches(id, game, source, label, proposal_id, condition, session_id, client_request_id, "
            "undoes_batch_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (batch_id, game, source, label, proposal_id, sess.get("condition"), sess.get("sessionId"),
             client_request_id, undoes_batch_id, ts),
        )
        for s, value in effective:
            old = current.get(s.id, {"value": None})["value"]
            conn.execute(
                "UPDATE setting_values SET value_json = ?, revision = revision + 1, updated_at = ? WHERE game = ? AND setting_id = ?",
                (dumps(value), ts, game, s.id),
            )
            rev = conn.execute("SELECT revision FROM setting_values WHERE game = ? AND setting_id = ?", (game, s.id)).fetchone()
            if rev is None:  # first write for a setting missing from the seed
                conn.execute("INSERT INTO setting_values(game, setting_id, value_json, revision, updated_at) VALUES (?,?,?,?,?)",
                             (game, s.id, dumps(value), 1, ts))
                rev_after = 1
            else:
                rev_after = int(rev["revision"])
            conn.execute(
                "INSERT INTO change_events(id, batch_id, game, setting_id, old_value_json, new_value_json, revision_after, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (new_id("evt"), batch_id, game, s.id, dumps(old), dumps(value), rev_after, ts),
            )
        conn.execute(
            "INSERT INTO game_state(game, revision) VALUES (?, 1) ON CONFLICT(game) DO UPDATE SET revision = revision + 1",
            (game,),
        )
        if sync_crosshair_profile and game == "valorant" and any(s.id.startswith("val.crosshair.") for s, _ in effective):
            from .crosshair import sync_active_profile_tx

            sync_active_profile_tx(self, conn)
        return self.batch_summary(conn, batch_id)

    # ------------------------------------------------------------------ public mutations
    def manual_change(self, game: str, changes: list[Change], *, client_request_id: Optional[str] = None,
                      label: Optional[str] = None) -> dict[str, Any]:
        if not changes:
            raise Invalid("No changes supplied")
        conn = self.connect()
        try:
            with write_tx(conn):
                is_preset = any(self.require_setting(game, c.setting_id).controlType == "preset" for c in changes)
                source = "preset" if is_preset else ("manual" if len(changes) == 1 else "manual_batch")
                if label is None:
                    if len(changes) == 1:
                        s = self.require_setting(game, changes[0].setting_id)
                        label = f"{s.exactLabel}"
                    else:
                        label = f"{len(changes)} settings"
                return self._apply_tx(conn, game, changes, source=source, label=label, enforce_locks=False,
                                      strict=False, client_request_id=client_request_id)
        finally:
            conn.close()

    def undo_batch(self, batch_id: str, *, client_request_id: Optional[str] = None) -> dict[str, Any]:
        conn = self.connect()
        try:
            with write_tx(conn):
                if client_request_id:
                    row = conn.execute("SELECT id FROM change_batches WHERE client_request_id = ?", (client_request_id,)).fetchone()
                    if row:
                        out = self.batch_summary(conn, row["id"])
                        out["idempotentReplay"] = True
                        return out
                batch = conn.execute("SELECT * FROM change_batches WHERE id = ?", (batch_id,)).fetchone()
                if batch is None:
                    raise NotFound(f"Unknown history entry {batch_id}")
                if batch["undone_by_batch_id"]:
                    raise Conflict("This change was already undone.", code="already_undone")
                if batch["source"] == "reset":
                    raise Invalid("Scenario resets cannot be undone from history.")
                game = batch["game"]
                events = conn.execute("SELECT * FROM change_events WHERE batch_id = ?", (batch_id,)).fetchall()
                current = self.values(conn, game)
                blocked = []
                for e in events:
                    cur = current.get(e["setting_id"])
                    if cur is None or int(cur["revision"]) != int(e["revision_after"]):
                        s = self.registry.setting(game, e["setting_id"])
                        label = s.exactLabel if s else e["setting_id"]
                        now_disp = display_value(s, cur["value"]) if (s and cur) else "?"
                        blocked.append({"settingId": e["setting_id"], "label": label,
                                        "reason": f"{label} has changed since (now {now_disp}). Undo the later change first."})
                if blocked:
                    raise Conflict("Undo would overwrite a later change. " + " ".join(b["reason"] for b in blocked),
                                   code="undo_conflict", details={"problems": blocked})
                changes = [Change(e["setting_id"], loads(e["old_value_json"])) for e in events]
                is_profile_switch = (batch["label"] or "").startswith("Crosshair profile: ")
                summary = self._apply_tx(conn, game, changes, source="undo", label=f"Undo: {batch['label'] or ''}".strip(),
                                         enforce_locks=False, strict=False, check_availability=False,
                                         client_request_id=client_request_id, undoes_batch_id=batch_id,
                                         sync_crosshair_profile=not is_profile_switch)
                if summary.get("batchId"):
                    conn.execute("UPDATE change_batches SET undone_by_batch_id = ? WHERE id = ?", (summary["batchId"], batch_id))
                return summary
        finally:
            conn.close()

    # ------------------------------------------------------------------ history
    def batch_summary(self, conn: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
        b = conn.execute("SELECT * FROM change_batches WHERE id = ?", (batch_id,)).fetchone()
        if b is None:
            raise NotFound(f"Unknown batch {batch_id}")
        game = b["game"]
        evs = conn.execute("SELECT * FROM change_events WHERE batch_id = ? ORDER BY rowid", (batch_id,)).fetchall()
        current_vals = self.values(conn, game)

        prop_row = None
        run_row = None
        user_msg_text: Optional[str] = None
        items_by_setting: dict[str, sqlite3.Row] = {}
        if b["proposal_id"]:
            prop_row = conn.execute("SELECT * FROM proposals WHERE id = ?", (b["proposal_id"],)).fetchone()
            if prop_row is not None:
                if prop_row["run_id"]:
                    run_row = conn.execute(
                        "SELECT id, mode, model, goal_excerpt FROM agent_runs WHERE id = ?",
                        (prop_row["run_id"],),
                    ).fetchone()
                    um = conn.execute(
                        "SELECT content_json FROM chat_messages WHERE run_id = ? AND role = 'user' LIMIT 1",
                        (prop_row["run_id"],),
                    ).fetchone()
                    if um:
                        user_msg_text = (loads(um["content_json"], {}) or {}).get("text")
                for pit in conn.execute(
                    "SELECT * FROM proposal_items WHERE proposal_id = ? ORDER BY position",
                    (b["proposal_id"],),
                ):
                    items_by_setting[pit["setting_id"]] = pit

        events = []
        undoable = not b["undone_by_batch_id"] and b["source"] != "reset"
        superseded_count = 0
        for e in evs:
            s = self.registry.setting(game, e["setting_id"])
            old, new = loads(e["old_value_json"]), loads(e["new_value_json"])
            cur = current_vals.get(e["setting_id"])
            cur_val = cur["value"] if cur is not None else None
            still_current = cur is not None and int(cur["revision"]) == int(e["revision_after"])
            if not still_current and not b["undone_by_batch_id"]:
                superseded_count += 1
            undoable = undoable and still_current
            pit = items_by_setting.get(e["setting_id"])
            events.append({
                "eventId": e["id"],
                "settingId": e["setting_id"],
                "label": s.exactLabel if s else e["setting_id"],
                "path": s.canonicalPath if s else e["setting_id"],
                "oldValue": old,
                "newValue": new,
                "oldDisplay": display_value(s, old) if s else str(old),
                "newDisplay": display_value(s, new) if s else str(new),
                "currentValue": cur_val,
                "currentDisplay": display_value(s, cur_val) if (s and cur is not None) else None,
                "revisionAfter": e["revision_after"],
                "stillCurrent": still_current,
                "why": pit["why"] if pit and pit["why"] else None,
                "tradeoff": pit["tradeoff"] if pit and pit["tradeoff"] else None,
                "basedOn": pit["based_on"] if pit and pit["based_on"] else None,
                "wasEditedByUser": bool(pit["edited_value_json"] is not None) if pit else False,
            })

        prop_keys = set(prop_row.keys()) if prop_row is not None else set()
        plan_obj = loads(prop_row["plan_json"], None) if (prop_row is not None and "plan_json" in prop_keys) else None
        ctx_snap = loads(prop_row["context_snapshot_json"], None) if (prop_row is not None and "context_snapshot_json" in prop_keys) else None
        raw_excerpt = run_row["goal_excerpt"] if run_row else None
        verbatim_req = user_msg_text or None
        is_excerpt = bool(verbatim_req is None and raw_excerpt is not None and len(raw_excerpt) >= 118)

        # Check whether an active session goal conflicts with this historical batch's recorded dimensions
        outdated_for_goal = False
        if prop_row is not None:
            hist_dims = set((ctx_snap or {}).get("goalDimensions") or [])
            if not hist_dims:
                for ev in events:
                    pit = items_by_setting.get(ev["settingId"])
                    if pit:
                        hist_dims.update(loads(pit["dimensions_json"], []))
            if hist_dims:
                sess = self.session(conn)
                cur_goals = conn.execute(
                    "SELECT dimensions_json FROM session_goals WHERE active = 1 AND session_id = ? AND game = ? ORDER BY created_at DESC LIMIT 1",
                    (sess["sessionId"], game),
                ).fetchone()
                if cur_goals:
                    from .profile import CONFLICT_PAIRS

                    cur_dims = set(loads(cur_goals["dimensions_json"], []))
                    if any(set(CONFLICT_PAIRS.get(cd, ())) & hist_dims for cd in cur_dims):
                        outdated_for_goal = True

        provenance = {
            "hasRecordedRationale": bool(
                prop_row is not None
                and (
                    (run_row is not None and bool(raw_excerpt))
                    or any(ev.get("why") or ev.get("basedOn") for ev in events)
                    or ("restaged_from_batch_id" in prop_keys and bool(prop_row["restaged_from_batch_id"]))
                )
            ),
            "userRequest": verbatim_req or raw_excerpt,
            "userRequestIsExcerpt": is_excerpt,
            "runId": prop_row["run_id"] if prop_row else None,
            "model": run_row["model"] if (run_row and run_row["mode"] == "ai") else None,
            "proposalTitle": prop_row["title"] if prop_row else None,
            "restagedFromBatchId": prop_row["restaged_from_batch_id"] if "restaged_from_batch_id" in prop_keys else None,
            "planReason": plan_obj.get("reason") if isinstance(plan_obj, dict) else None,
        }
        return {
            "batchId": b["id"],
            "game": game,
            "source": b["source"],
            "sourceLabel": SOURCE_LABELS.get(b["source"], b["source"]),
            "label": b["label"],
            "proposalId": b["proposal_id"],
            "condition": b["condition"],
            "createdAt": b["created_at"],
            "undoesBatchId": b["undoes_batch_id"],
            "undoneByBatchId": b["undone_by_batch_id"],
            "undoable": undoable,
            "superseded": bool(not b["undone_by_batch_id"] and superseded_count > 0),
            "supersededCount": superseded_count,
            "outdatedForCurrentGoal": outdated_for_goal,
            "provenance": provenance,
            "events": events,
            "gameRevision": self.game_revision(conn, game),
            "values": {e["settingId"]: {"value": e["newValue"], "revision": e["revisionAfter"]} for e in events},
        }

    def history(self, game: str, limit: int = 100) -> list[dict[str, Any]]:
        self.require_game(game)
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT id FROM change_batches WHERE game = ? AND source != 'reset' ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (game, limit)).fetchall()
            return [self.batch_summary(conn, r["id"]) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------ pins & locks
    def set_flag(self, table: str, game: str, setting_id: str, on: bool) -> list[str]:
        assert table in ("pins", "locks")
        s = self.require_setting(game, setting_id)
        if table == "locks" and s.controlType == "preset":
            raise Invalid("Lock individual video settings instead of the preset.")
        conn = self.connect()
        try:
            with write_tx(conn):
                if on:
                    conn.execute(f"INSERT OR IGNORE INTO {table}(game, setting_id, created_at) VALUES (?,?,?)",
                                 (game, setting_id, now_iso()))
                else:
                    conn.execute(f"DELETE FROM {table} WHERE game = ? AND setting_id = ?", (game, setting_id))
            return self.pins(conn, game) if table == "pins" else self.locks(conn, game)
        finally:
            conn.close()
