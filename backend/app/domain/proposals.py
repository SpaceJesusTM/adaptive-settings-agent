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
from .profile import CONFLICT_PAIRS, ProfileService
from .store import Change, Store
from .values import ValueError_, availability_problem, display_value, normalize_value, values_equal

MAX_PROPOSAL_ITEMS = 60
SOURCES = {"ai": "ai_applied", "fallback": "fallback_applied", "rules": "rule_applied", "history": "history_applied"}
SOURCE_LABELS = {
    "ai": "Local AI suggestion",
    "fallback": "Offline fallback (not AI)",
    "rules": "Rule-based suggestion",
    "history": "Restaged from history",
}


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
        plan_obj = loads(p["plan_json"], None) if "plan_json" in keys else None
        ctx_snap = loads(p["context_snapshot_json"], None) if "context_snapshot_json" in keys else None

        freshness_status = "consistent"
        freshness_warning: Optional[str] = None
        if p["status"] == "pending":
            cur_goals = self.profile.session_goals(conn, game)
            cur_goal = cur_goals[0] if cur_goals else None
            snap_goal_dims = list((ctx_snap or {}).get("goalDimensions") or (plan_obj or {}).get("inferredDimensions") or [])
            snap_goal_text = (ctx_snap or {}).get("goalText")
            item_dims = list(dict.fromkeys(d for it in items if it["status"] == "pending" for d in it.get("dimensions", [])))
            compare_dims = snap_goal_dims or item_dims

            if p["source"] == "history" and (item_dims or (plan_obj or {}).get("inferredDimensions")) and cur_goal:
                hist_dims = item_dims or list((plan_obj or {}).get("inferredDimensions") or [])
                cur_dims = set(cur_goal.get("dimensions") or [])
                has_conflict = any(set(CONFLICT_PAIRS.get(cd, ())) & set(hist_dims) for cd in cur_dims)
                if has_conflict or (cur_dims and not (cur_dims & set(hist_dims))):
                    freshness_status = "historical_preference"
                    freshness_warning = (
                        f"Restaged from an earlier setup targeting {', '.join(DIMENSION_LABELS.get(d, d) for d in hist_dims[:2])}. "
                        f"Your current goal focuses on {', '.join(DIMENSION_LABELS.get(d, d) for d in cur_goal['dimensions'][:2])} — review carefully before applying."
                    )
            elif cur_goal and compare_dims:
                cur_dims = set(cur_goal.get("dimensions") or [])
                has_conflict = any(set(CONFLICT_PAIRS.get(cd, ())) & set(compare_dims) for cd in cur_dims)
                shifted = bool(cur_dims) and not (cur_dims & set(compare_dims))
                if has_conflict or shifted or (snap_goal_text and cur_goal.get("text") and snap_goal_text != cur_goal["text"] and has_conflict):
                    freshness_status = "outdated_goal"
                    prior_desc = f"“{snap_goal_text}”" if snap_goal_text else ", ".join(DIMENSION_LABELS.get(d, d) for d in compare_dims[:2])
                    cur_desc = f"“{cur_goal['text']}”" if cur_goal.get("text") else ", ".join(DIMENSION_LABELS.get(d, d) for d in cur_goal["dimensions"][:2])
                    freshness_warning = (
                        f"Prepared when your goal was {prior_desc}. Your current goal favors {cur_desc}. "
                        "Review these recommendations or reject them before applying."
                    )

            if freshness_status == "consistent" and any(it["stale"] for it in items if it["status"] == "pending"):
                freshness_status = "technically_stale"
                freshness_warning = "One or more settings in this draft changed since staging; rebase or uncheck stale items before applying."

        return {"id": p["id"], "game": game, "source": p["source"], "sourceLabel": SOURCE_LABELS.get(p["source"], p["source"]),
                "runId": p["run_id"], "title": p["title"], "status": p["status"], "createdAt": p["created_at"],
                "updatedAt": p["updated_at"], "appliedBatchId": p["applied_batch_id"],
                "autoStaged": bool(p["auto_staged"]) if "auto_staged" in keys else False,
                "restagedFromBatchId": p["restaged_from_batch_id"] if "restaged_from_batch_id" in keys else None,
                "generatedGoalText": (ctx_snap or {}).get("goalText"),
                "generatedGoalDimensions": list((ctx_snap or {}).get("goalDimensions") or []),
                "freshnessStatus": freshness_status,
                "freshnessWarning": freshness_warning,
                "plan": plan_obj,
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
        restaged_from_batch_id: Optional[str] = None,
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
        ctx_snap = self.profile.snapshot_context(conn, game)
        conn.execute(
            "INSERT INTO proposals(id, game, source, run_id, title, status, condition, session_id, created_at, updated_at, "
            "plan_json, auto_staged, restaged_from_batch_id, context_snapshot_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, game, source, run_id, (title or "Suggested changes")[:120], "pending" if any_pending else "closed",
             sess.get("condition"), sess.get("sessionId"), ts, ts, dumps(plan) if plan is not None else None,
             1 if auto_staged else 0, restaged_from_batch_id, dumps(ctx_snap)),
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
        return {"proposalId": pid, "stagedCount": int(cnt), "alreadyPendingCount": already_pending_count,
                "idempotentReplay": False}

    def restage_from_batch(self, batch_id: str) -> dict[str, Any]:
        """Construct a new editable proposal from a historical batch without mutating active settings."""
        conn = self.store.connect()
        try:
            b = conn.execute("SELECT * FROM change_batches WHERE id = ?", (batch_id,)).fetchone()
            if b is None:
                raise NotFound(f"Unknown history entry {batch_id}")
            if b["source"] == "reset":
                raise Invalid("Scenario resets cannot be restaged from history.")
            game = b["game"]
            evs = conn.execute("SELECT * FROM change_events WHERE batch_id = ? ORDER BY rowid", (batch_id,)).fetchall()
            if not evs:
                raise Invalid("This history entry contains no setting changes.")

            orig_items: dict[str, sqlite3.Row] = {}
            if b["proposal_id"]:
                for pit in conn.execute("SELECT * FROM proposal_items WHERE proposal_id = ?", (b["proposal_id"],)):
                    orig_items[pit["setting_id"]] = pit

            current_vals = self.store.values(conn, game)
            flat = {k: v["value"] for k, v in current_vals.items()}
            hw = self.store.hardware(conn)
            stage_items: list[dict[str, Any]] = []
            already_aligned: list[dict[str, Any]] = []
            manual_considerations: list[dict[str, Any]] = []
            locked_items: list[dict[str, Any]] = []
            unavailable_items: list[dict[str, Any]] = []

            origin_label = self.store.batch_summary(conn, batch_id)["sourceLabel"]
            created_day = str(b["created_at"])[:10]
            fallback_basis = f"Restaged from {origin_label} ({created_day})"

            for e in evs:
                s = self.store.registry.setting(game, e["setting_id"])
                if s is None:
                    continue
                target_raw = loads(e["new_value_json"])
                cur = current_vals.get(s.id, {"value": None, "revision": 0})
                cur_disp = display_value(s, cur["value"])
                target_disp = display_value(s, target_raw)
                pit = orig_items.get(s.id)

                if values_equal(cur["value"], target_raw):
                    already_aligned.append({
                        "settingId": s.id,
                        "label": s.exactLabel,
                        "path": s.canonicalPath,
                        "category": s.category,
                        "currentDisplay": cur_disp,
                        "why": pit["why"] if pit and pit["why"] else f"Matches your earlier target ({target_disp}).",
                        "whatItDoes": s.description,
                        "tradeoffs": s.riskOrTradeoffs,
                    })
                    continue

                if not s.aiProposable or s.controlType in ("keybind", "preset", "color"):
                    manual_considerations.append({
                        "settingId": s.id,
                        "label": s.exactLabel,
                        "path": s.canonicalPath,
                        "category": s.category,
                        "currentDisplay": cur_disp,
                        "reason": f"Personal or manual control (earlier value: {target_disp}). Adjust directly if you still want that target.",
                        "whatItDoes": s.description,
                        "tradeoffs": s.riskOrTradeoffs,
                    })
                    continue

                try:
                    normalized_target = normalize_value(s, target_raw, strict=True)
                except ValueError_ as exc:
                    unavailable_items.append({
                        "settingId": s.id,
                        "label": s.exactLabel,
                        "path": s.canonicalPath,
                        "reason": str(exc),
                    })
                    continue

                if self.store.is_locked(conn, game, s.id):
                    locked_items.append({
                        "settingId": s.id,
                        "label": s.exactLabel,
                        "path": s.canonicalPath,
                        "reason": f"Locked from proposed changes (earlier value: {target_disp}).",
                    })
                    continue

                prob = availability_problem(self.store.registry, s, {**flat, s.id: normalized_target}, hw)
                if prob:
                    unavailable_items.append({
                        "settingId": s.id,
                        "label": s.exactLabel,
                        "path": s.canonicalPath,
                        "reason": prob,
                    })
                    continue

                derived_dims = loads(pit["dimensions_json"], []) if pit else []
                if not derived_dims:
                    derived_dims = [
                        h.dimension
                        for h in s.goalHints
                        if any(values_equal(normalized_target, v) for v in h.prefer)
                    ]
                stage_items.append({
                    "settingId": s.id,
                    "proposedValue": normalized_target,
                    "why": pit["why"] if pit and pit["why"] else None,
                    "tradeoff": pit["tradeoff"] if pit and pit["tradeoff"] else s.riskOrTradeoffs,
                    "confidence": pit["confidence"] if pit and pit["confidence"] else None,
                    "dimensions": list(dict.fromkeys(derived_dims)),
                    "basedOn": pit["based_on"] if pit and pit["based_on"] else fallback_basis,
                })

            hist_inferred = list(dict.fromkeys(d for it in stage_items for d in it.get("dimensions", [])))
            plan_meta = {
                "scope": "focused" if len(evs) <= 3 else "broad_optimization",
                "maxRecommendations": len(evs),
                "includeMinor": True,
                "isSupplement": False,
                "reason": (
                    f"Restaged from {origin_label} ({created_day}). "
                    f"{len(stage_items)} change(s) ready to review, {len(already_aligned)} already matching that configuration."
                ),
                "inferredDimensions": hist_inferred,
                "autoStage": False,
                "partialCoverage": False,
                "batchesCompleted": 1,
                "batchesTotal": 1,
                "restagedFromBatchId": batch_id,
                "coverage": {
                    "evaluatedCount": len(evs),
                    "eligibleCount": len(stage_items),
                    "proposedCount": len(stage_items),
                    "alreadyAlignedCount": len(already_aligned),
                    "alreadyStagedCount": 0,
                    "lockedCount": len(locked_items),
                    "unavailableCount": len(unavailable_items),
                    "manualCount": len(manual_considerations),
                    "byCategory": {},
                },
                "alreadyAlignedItems": already_aligned,
                "manualConsiderations": manual_considerations,
                "lockedItems": locked_items,
                "unavailableItems": unavailable_items,
            }

            if not stage_items:
                return {
                    "proposal": None,
                    "stagedCount": 0,
                    "alreadyAlignedItems": already_aligned,
                    "manualConsiderations": manual_considerations,
                    "lockedItems": locked_items,
                    "unavailableItems": unavailable_items,
                    "message": (
                        "All restageable settings from that entry already match their earlier values"
                        if already_aligned and not (locked_items or manual_considerations or unavailable_items)
                        else "No actionable changes could be restaged automatically; see current status below."
                    ),
                }

            with write_tx(conn):
                pid = self._insert_proposal_tx(
                    conn,
                    game,
                    source="history",
                    run_id=None,
                    title=f"Restaged: {(b['label'] or 'Previous changes')[:95]}",
                    items=stage_items[:MAX_PROPOSAL_ITEMS],
                    auto_staged=False,
                    plan=plan_meta,
                    restaged_from_batch_id=batch_id,
                )
            proposal = self.get(pid)
            return {
                "proposal": proposal,
                "stagedCount": len(stage_items),
                "alreadyAlignedItems": already_aligned,
                "manualConsiderations": manual_considerations,
                "lockedItems": locked_items,
                "unavailableItems": unavailable_items,
                "message": f"Prepared {len(stage_items)} change(s) in Changes for review — nothing applied yet.",
            }
        finally:
            conn.close()

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
                edited_json = None if values_equal(v, loads(it["proposed_value_json"])) else dumps(v)
                conn.execute("UPDATE proposal_items SET edited_value_json = ?, status_reason = NULL WHERE id = ?", (edited_json, item_id))
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
