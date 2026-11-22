"""Proposal engine: staged, revision-checked, all-or-nothing approval of suggested changes.

Lifecycle: suggested (chat / Relevant Now card, not stored here) -> staged (pending item) -> applied |
rejected. Baseline value and revision are captured server-side at staging time from the store - never from
the client or the model - and re-checked at apply time. A bundle either applies completely or returns a
409 that explains every blocking item; items stay pending so the user can rebase, unlock or deselect.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..catalog.schema import DIMENSION_LABELS
from .db import dumps, loads, new_id, now_iso, write_tx
from .errors import Conflict, Invalid, NotFound
from .profile import ProfileService
from .store import Change, Store
from .values import ValueError_, availability_problem, display_value, normalize_value, values_equal

MAX_PROPOSAL_ITEMS = 60
SOURCES = {"ai": "ai_applied", "fallback": "fallback_applied", "rules": "rule_applied"}
SOURCE_LABELS = {"ai": "Local AI suggestion", "fallback": "Offline fallback (not AI)", "rules": "Rule-based suggestion"}


class ProposalService:
    def __init__(self, store: Store, profile: ProfileService):
        self.store = store
        self.profile = profile

    # ------------------------------------------------------------------ views
    def view(self, conn: sqlite3.Connection, proposal_id: str) -> dict[str, Any]:
        p = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if p is None:
            raise NotFound(f"Unknown proposal {proposal_id}")
        game = p["game"]
        values = self.store.values(conn, game)
        flat = {k: v["value"] for k, v in values.items()}
        hw = self.store.hardware(conn)
        items = []
        for r in conn.execute("SELECT * FROM proposal_items WHERE proposal_id = ? ORDER BY position", (proposal_id,)):
            s = self.store.registry.setting(game, r["setting_id"])
            if s is None:
                continue
            baseline = loads(r["baseline_value_json"])
            proposed = loads(r["proposed_value_json"])
            edited = loads(r["edited_value_json"]) if r["edited_value_json"] is not None else None
            effective = edited if edited is not None else proposed
            cur = values.get(s.id, {"value": None, "revision": 0})
            stale = int(cur["revision"]) != int(r["baseline_revision"])
            items.append({
                "id": r["id"], "settingId": s.id, "label": s.exactLabel, "path": s.canonicalPath,
                "category": s.category, "section": s.section, "applyMode": s.applyMode,
                "tabId": s.tabId, "subtabId": s.subtabId,
                "controlType": s.controlType, "validOptions": [o.model_dump() for o in (s.validOptions or [])],
                "min": s.min, "max": s.max, "step": s.step, "display": s.display, "unit": s.unit,
                "baselineValue": baseline, "baselineDisplay": display_value(s, baseline),
                "baselineRevision": r["baseline_revision"],
                "proposedValue": proposed, "proposedDisplay": display_value(s, proposed),
                "editedValue": edited, "effectiveValue": effective, "effectiveDisplay": display_value(s, effective),
                "currentValue": cur["value"], "currentDisplay": display_value(s, cur["value"]),
                "currentRevision": cur["revision"], "stale": stale,
                "locked": self.store.is_locked(conn, game, s.id),
                "unavailableReason": availability_problem(self.store.registry, s, {**flat, s.id: effective}, hw),
                "status": r["status"], "statusReason": r["status_reason"],
                "why": r["why"], "tradeoff": r["tradeoff"], "whatItDoes": s.description,
                "whatItDoesSource": s.descriptionSource, "sourceURL": s.sourceURL,
                "confidence": r["confidence"], "dimensions": loads(r["dimensions_json"], []), "basedOn": r["based_on"],
            })
        keys = set(p.keys())
        return {"id": p["id"], "game": game, "source": p["source"], "sourceLabel": SOURCE_LABELS.get(p["source"], p["source"]),
                "runId": p["run_id"], "title": p["title"], "status": p["status"], "createdAt": p["created_at"],
                "updatedAt": p["updated_at"], "appliedBatchId": p["applied_batch_id"],
                "autoStaged": bool(p["auto_staged"]) if "auto_staged" in keys else False,
                "plan": loads(p["plan_json"], None) if "plan_json" in keys else None,
                "items": items}

    def list(self, game: str, status: Optional[str] = None) -> list[dict[str, Any]]:
        self.store.require_game(game)
        conn = self.store.connect()
        try:
            q = "SELECT id FROM proposals WHERE game = ?"
            args: list[Any] = [game]
            if status:
                q += " AND status = ?"
                args.append(status)
            q += " ORDER BY created_at DESC LIMIT 50"
            return [self.view(conn, r["id"]) for r in conn.execute(q, args).fetchall()]
        finally:
            conn.close()

    def get(self, proposal_id: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            return self.view(conn, proposal_id)
        finally:
            conn.close()

    # ------------------------------------------------------------------ staging
    def _insert_proposal_tx(
        self,
        conn: sqlite3.Connection,
        game: str,
        *,
        source: str,
        run_id: Optional[str],
        title: Optional[str],
        items: list[dict[str, Any]],
        auto_staged: bool = False,
        plan: Optional[dict[str, Any]] = None,
    ) -> str:
        """Validate items, capture server-side baselines and insert proposal rows inside an active write_tx."""
        if source not in SOURCES:
            raise Invalid("source must be ai, fallback or rules")
        if not items:
            raise Invalid("A proposal needs at least one item")
        if len(items) > MAX_PROPOSAL_ITEMS:
            raise Invalid(f"At most {MAX_PROPOSAL_ITEMS} changes can be staged in one proposal")
        self.store.require_game(game)
        values = self.store.values(conn, game)
        flat = {k: v["value"] for k, v in values.items()}
        hw = self.store.hardware(conn)
        pid = new_id("prop")
        ts = now_iso()
        sess = self.store.session(conn)
        staged_rows = []
        seen: set[str] = set()
        for pos, it in enumerate(items):
            s = self.store.require_setting(game, str(it.get("settingId", "")))
            if s.id in seen:
                raise Invalid(f"{s.exactLabel} appears twice in the proposal")
            seen.add(s.id)
            if not s.aiProposable or s.controlType in ("keybind", "preset", "color"):
                raise Invalid(f"{s.exactLabel} cannot be changed through suggestions", code="not_proposable")
            try:
                value = normalize_value(s, it.get("proposedValue"), strict=True)
            except ValueError_ as exc:
                raise Invalid(str(exc), code="invalid_value", details={"settingId": s.id}) from exc
            cur = values.get(s.id, {"value": None, "revision": 0})
            status, reason = "pending", None
            if self.store.is_locked(conn, game, s.id):
                status, reason = "blocked", f"{s.exactLabel} is locked from AI changes."
            elif values_equal(cur["value"], value):
                status, reason = "blocked", f"{s.exactLabel} is already {display_value(s, value)}."
            else:
                problem = availability_problem(self.store.registry, s, {**flat, s.id: value}, hw)
                if problem:
                    status, reason = "blocked", problem
            dims = [d for d in (it.get("dimensions") or []) if d in DIMENSION_LABELS]
            staged_rows.append((new_id("item"), pid, pos, s.id, dumps(cur["value"]), int(cur["revision"]),
                                dumps(value), None, status, reason, (it.get("why") or "")[:700],
                                (it.get("tradeoff") or None), it.get("confidence"), dumps(dims),
                                (it.get("basedOn") or None)))
        any_pending = any(r[8] == "pending" for r in staged_rows)
        conn.execute(
            "INSERT INTO proposals(id, game, source, run_id, title, status, condition, session_id, created_at, updated_at, plan_json, auto_staged) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, game, source, run_id, (title or "Suggested changes")[:120], "pending" if any_pending else "closed",
             sess.get("condition"), sess.get("sessionId"), ts, ts, dumps(plan) if plan is not None else None,
             1 if auto_staged else 0),
        )
        conn.executemany(
            "INSERT INTO proposal_items(id, proposal_id, position, setting_id, baseline_value_json, baseline_revision, "
            "proposed_value_json, edited_value_json, status, status_reason, why, tradeoff, confidence, dimensions_json, based_on) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", staged_rows
        )
        return pid

    def create(self, game: str, *, source: str, run_id: Optional[str], title: Optional[str],
               items: list[dict[str, Any]], plan: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self.store.require_game(game)
        conn = self.store.connect()
        try:
            with write_tx(conn):
                pid = self._insert_proposal_tx(conn, game, source=source, run_id=run_id, title=title, items=items,
                                               auto_staged=False, plan=plan)
            return self.view(conn, pid)
        finally:
            conn.close()

    def auto_stage_for_run(
        self,
        conn: sqlite3.Connection,
        game: str,
        *,
        source: str,
        run_id: str,
        title: Optional[str],
        items: list[dict[str, Any]],
        plan: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Idempotently auto-stage one draft proposal for a completed chat run inside an active write_tx.

        Never mutates setting values and never duplicates or overwrites existing pending items.
        """
        existing = conn.execute(
            "SELECT id FROM proposals WHERE run_id = ? AND auto_staged = 1", (run_id,)
        ).fetchone()
        if existing is not None:
            cnt = conn.execute(
                "SELECT COUNT(*) AS n FROM proposal_items WHERE proposal_id = ? AND status = 'pending'",
                (existing["id"],),
            ).fetchone()["n"]
            return {"proposalId": existing["id"], "stagedCount": int(cnt), "alreadyPendingCount": 0, "idempotentReplay": True}

        pending_ids = {
            r["setting_id"]
            for r in conn.execute(
                "SELECT i.setting_id FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
                "WHERE p.game = ? AND p.status = 'pending' AND i.status = 'pending'",
                (game,),
            )
        }
        filtered_items = [it for it in items if str(it.get("settingId", "")) not in pending_ids]
        already_pending_count = len(items) - len(filtered_items)
        if not filtered_items:
            return {"proposalId": None, "stagedCount": 0, "alreadyPendingCount": already_pending_count, "idempotentReplay": False}

        pid = self._insert_proposal_tx(
            conn,
            game,
            source=source,
            run_id=run_id,
            title=title,
            items=filtered_items[:MAX_PROPOSAL_ITEMS],
            auto_staged=True,
            plan=plan,
        )
        cnt = conn.execute(
            "SELECT COUNT(*) AS n FROM proposal_items WHERE proposal_id = ? AND status = 'pending'", (pid,)
        ).fetchone()["n"]
        return {
            "proposalId": pid,
            "stagedCount": int(cnt),
            "alreadyPendingCount": already_pending_count,
            "idempotentReplay": False,
        }

    def _pending_item(self, conn: sqlite3.Connection, proposal_id: str, item_id: str) -> sqlite3.Row:
        p = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if p is None:
            raise NotFound("Unknown proposal")
        it = conn.execute("SELECT * FROM proposal_items WHERE id = ? AND proposal_id = ?", (item_id, proposal_id)).fetchone()
        if it is None:
            raise NotFound("Unknown proposal item")
        if p["status"] != "pending" or it["status"] != "pending":
            raise Conflict("This item is no longer pending.", code="not_pending")
        return it

    def edit_item(self, proposal_id: str, item_id: str, value: Any) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                it = self._pending_item(conn, proposal_id, item_id)
                game = conn.execute("SELECT game FROM proposals WHERE id = ?", (proposal_id,)).fetchone()["game"]
                s = self.store.require_setting(game, it["setting_id"])
                try:
                    v = normalize_value(s, value, strict=False)  # user edit: snap like a manual control
                except ValueError_ as exc:
                    raise Invalid(str(exc), code="invalid_value") from exc
                conn.execute("UPDATE proposal_items SET edited_value_json = ?, status_reason = NULL WHERE id = ?", (dumps(v), item_id))
                conn.execute("UPDATE proposals SET updated_at = ? WHERE id = ?", (now_iso(), proposal_id))
            return self.view(conn, proposal_id)
        finally:
            conn.close()

    def rebase_item(self, proposal_id: str, item_id: str) -> dict[str, Any]:
        """User acknowledges that the setting changed since staging and keeps the suggestion against the new value."""
        conn = self.store.connect()
        try:
            with write_tx(conn):
                it = self._pending_item(conn, proposal_id, item_id)
                game = conn.execute("SELECT game FROM proposals WHERE id = ?", (proposal_id,)).fetchone()["game"]
                cur = self.store.values(conn, game)[it["setting_id"]]
                conn.execute("UPDATE proposal_items SET baseline_value_json = ?, baseline_revision = ?, status_reason = NULL WHERE id = ?",
                             (dumps(cur["value"]), int(cur["revision"]), item_id))
            return self.view(conn, proposal_id)
        finally:
            conn.close()

    # ------------------------------------------------------------------ approval
    def apply(self, proposal_id: str, item_ids: list[str], idempotency_key: Optional[str]) -> dict[str, Any]:
        if not item_ids:
            raise Invalid("Select at least one change to apply")
        conn = self.store.connect()
        try:
            try:
                with write_tx(conn):
                    if idempotency_key:
                        row = conn.execute("SELECT id FROM change_batches WHERE client_request_id = ?", (idempotency_key,)).fetchone()
                        if row:
                            return {"proposal": self.view(conn, proposal_id), "batch": self.store.batch_summary(conn, row["id"]),
                                    "idempotentReplay": True}
                    p = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
                    if p is None:
                        raise NotFound("Unknown proposal")
                    if p["status"] != "pending":
                        raise Conflict("This proposal is no longer pending (already applied or rejected).", code="not_pending")
                    rows = {r["id"]: r for r in conn.execute("SELECT * FROM proposal_items WHERE proposal_id = ?", (proposal_id,))}
                    selected = []
                    for iid in dict.fromkeys(item_ids):
                        r = rows.get(iid)
                        if r is None:
                            raise Invalid(f"Item {iid} is not part of this proposal")
                        if r["status"] != "pending":
                            raise Conflict(f"Item {iid} is not pending.", code="not_pending")
                        selected.append(r)
                    changes = [Change(r["setting_id"],
                                      loads(r["edited_value_json"]) if r["edited_value_json"] is not None else loads(r["proposed_value_json"]),
                                      expected_revision=int(r["baseline_revision"])) for r in selected]
                    summary = self.store._apply_tx(conn, p["game"], changes, source=SOURCES[p["source"]],
                                                   label=p["title"], enforce_locks=True, strict=True,
                                                   proposal_id=proposal_id, client_request_id=idempotency_key)
                    ts = now_iso()
                    for idx, r in enumerate(selected):
                        conn.execute("UPDATE proposal_items SET status = 'applied', status_reason = NULL WHERE id = ?", (r["id"],))
                        s = self.store.registry.setting(p["game"], r["setting_id"])
                        dims = loads(r["dimensions_json"], []) or [None]
                        for d in dims:
                            self.profile.add_evidence(conn, kind="applied", dimension=d, game=p["game"], setting_id=r["setting_id"],
                                                      proposal_id=proposal_id,
                                                      detail=f"Applied {s.exactLabel if s else r['setting_id']}: "
                                                             f"{display_value(s, loads(r['baseline_value_json'])) if s else ''} -> "
                                                             f"{display_value(s, changes[idx].value) if s else ''}")
                    remaining = conn.execute("SELECT COUNT(*) AS n FROM proposal_items WHERE proposal_id = ? AND status = 'pending'",
                                             (proposal_id,)).fetchone()["n"]
                    conn.execute("UPDATE proposals SET status = ?, applied_batch_id = ?, updated_at = ? WHERE id = ?",
                                 ("pending" if remaining else "applied", summary.get("batchId"), ts, proposal_id))
                    return {"proposal": self.view(conn, proposal_id), "batch": summary}
            except (Conflict, Invalid) as exc:
                # Nothing was applied (transaction rolled back). Record why on the items so the UI can explain.
                problems = (exc.details or {}).get("problems", []) if isinstance(exc.details, dict) else []
                if problems:
                    with write_tx(conn):
                        for prob in problems:
                            conn.execute("UPDATE proposal_items SET status_reason = ? WHERE proposal_id = ? AND setting_id = ? AND status = 'pending'",
                                         (prob.get("reason"), proposal_id, prob.get("settingId")))
                raise
        finally:
            conn.close()

    def reject(self, proposal_id: str, item_ids: Optional[list[str]], reason: Optional[str]) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                p = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
                if p is None:
                    raise NotFound("Unknown proposal")
                rows = conn.execute("SELECT * FROM proposal_items WHERE proposal_id = ? AND status = 'pending'", (proposal_id,)).fetchall()
                targets = [r for r in rows if item_ids is None or r["id"] in set(item_ids)]
                for r in targets:
                    conn.execute("UPDATE proposal_items SET status = 'rejected', status_reason = ? WHERE id = ?",
                                 ((reason or "Rejected by user")[:200], r["id"]))
                    s = self.store.registry.setting(p["game"], r["setting_id"])
                    for d in loads(r["dimensions_json"], []) or [None]:
                        self.profile.add_evidence(conn, kind="rejected", dimension=d, game=p["game"], setting_id=r["setting_id"],
                                                  proposal_id=proposal_id,
                                                  detail=f"Rejected {s.exactLabel if s else r['setting_id']} -> "
                                                         f"{display_value(s, loads(r['proposed_value_json'])) if s else ''}"
                                                         + (f" ({reason})" if reason else ""))
                remaining = conn.execute("SELECT COUNT(*) AS n FROM proposal_items WHERE proposal_id = ? AND status = 'pending'",
                                         (proposal_id,)).fetchone()["n"]
                applied = conn.execute("SELECT COUNT(*) AS n FROM proposal_items WHERE proposal_id = ? AND status = 'applied'",
                                       (proposal_id,)).fetchone()["n"]
                status = "pending" if remaining else ("applied" if applied else "rejected")
                conn.execute("UPDATE proposals SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), proposal_id))
            return self.view(conn, proposal_id)
        finally:
            conn.close()
