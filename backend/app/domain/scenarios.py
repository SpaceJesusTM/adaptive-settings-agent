"""Deterministic demo scenarios, non-destructive reset, and state export/import.

Every reset first writes a JSON backup of the complete current state to data/local/backups/, so a reset
never destroys local work. Two reset modes exist:
* ``full``     - restore the scenario's experimental initial state (values, profile, pins, locks, history);
* ``ai_only``  - keep setting values, history, pins, locks and durable preferences, but clear AI/session
                 artefacts (proposals, chat, Relevant Now, run traces, context events, session goals).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .db import dumps, new_id, now_iso, write_tx
from .errors import Invalid, NotFound
from .store import DEFAULT_HARDWARE, Store
from .values import ValueError_, normalize_value

ALL_TABLES = [
    "setting_values", "game_state", "change_events", "change_batches", "pins", "locks", "proposal_items",
    "proposals", "preferences", "evidence", "session_goals", "dismissals", "relevant_now", "context_events",
    "chat_messages", "agent_runs", "valorant_crosshair_profiles", "personal_setup_facts", "onboarding_state",
    "followup_resolutions", "kv",
]
AI_TABLES = ["proposal_items", "proposals", "relevant_now", "chat_messages", "agent_runs", "context_events",
             "session_goals", "dismissals", "followup_resolutions"]


def list_scenarios(scenario_dir: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(scenario_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        out.append({"name": data["name"], "title": data.get("title", data["name"]),
                    "description": data.get("description", ""), "synthetic": data.get("synthetic", True)})
    return out


def load_scenario(scenario_dir: Path, name: str) -> dict[str, Any]:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_")
    path = scenario_dir / f"{safe}.json"
    if not safe or not path.is_file():
        raise NotFound(f"Unknown scenario '{name}'")
    return json.loads(path.read_text(encoding="utf-8"))


def export_state(store: Store) -> dict[str, Any]:
    conn = store.connect()
    try:
        out: dict[str, Any] = {"format": "csc2524-state", "version": 2, "exportedAt": now_iso(), "tables": {}}
        for t in ALL_TABLES:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            out["tables"][t] = [dict(r) for r in rows]
        return out
    finally:
        conn.close()


def write_backup(store: Store, backup_dir: Path, reason: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_iso().replace(":", "").replace("-", "").replace(".", "")
    path = backup_dir / f"backup_{stamp}_{reason}.json"
    path.write_text(json.dumps(export_state(store), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _ensure_default_crosshair_profile(store: Store, conn, ts: str) -> None:
    count = conn.execute("SELECT COUNT(*) AS n FROM valorant_crosshair_profiles").fetchone()["n"]
    if count > 0:
        return
    vals = store.flat_values(conn, "valorant")
    xhair_settings = {k: v for k, v in vals.items() if k.startswith("val.crosshair.")}
    conn.execute(
        "INSERT INTO valorant_crosshair_profiles(id, name, settings_json, is_active, created_at, updated_at) "
        "VALUES (?,?,?,1,?,?)",
        (new_id("xhp"), "Default", dumps(xhair_settings), ts, ts),
    )


def sync_catalog_defaults(store: Store) -> int:
    """Seed any newly-added catalogue settings into existing DBs without overwriting user state."""
    conn = store.connect()
    inserted = 0
    ts = now_iso()
    try:
        with write_tx(conn):
            for game in store.registry.games:
                for s in store.registry.settings(game):
                    if s.controlType == "preset":
                        continue
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO setting_values(game, setting_id, value_json, revision, updated_at) "
                        "VALUES (?,?,?,0,?)",
                        (game, s.id, dumps(s.sampleInitialValue), ts),
                    )
                    inserted += cur.rowcount
            _ensure_default_crosshair_profile(store, conn, ts)
        return inserted
    finally:
        conn.close()


def import_state(store: Store, data: dict[str, Any]) -> None:
    if data.get("format") != "csc2524-state":
        raise Invalid("Not a csc2524 state export")
    tables = data.get("tables", {})
    conn = store.connect()
    try:
        with write_tx(conn):
            for t in ALL_TABLES:
                conn.execute(f"DELETE FROM {t}")
            for t in reversed(ALL_TABLES):  # parents before children
                for row in tables.get(t, []):
                    cols = list(row)
                    conn.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                                 [row[c] for c in cols])
            _ensure_default_crosshair_profile(store, conn, now_iso())
    finally:
        conn.close()
    sync_catalog_defaults(store)


def _seed_values(store: Store, conn, scenario: dict[str, Any]) -> None:
    overrides: dict[str, dict[str, Any]] = scenario.get("values", {})
    ts = now_iso()
    for game in store.registry.games:
        game_over = overrides.get(game, {})
        for s in store.registry.settings(game):
            if s.controlType == "preset":
                continue
            value = s.sampleInitialValue
            if s.id in game_over:
                try:
                    value = normalize_value(s, game_over[s.id], strict=False)
                except ValueError_ as exc:
                    raise Invalid(f"Scenario value for {s.id} invalid: {exc}") from exc
            conn.execute("INSERT INTO setting_values(game, setting_id, value_json, revision, updated_at) VALUES (?,?,?,?,?)",
                         (game, s.id, dumps(value), 0, ts))
        unknown = set(game_over) - {s.id for s in store.registry.settings(game)}
        if unknown:
            raise Invalid(f"Scenario sets unknown {game} settings: {sorted(unknown)}")
        conn.execute("INSERT INTO game_state(game, revision) VALUES (?, 0)", (game,))


def reset(store: Store, scenario_dir: Path, backup_dir: Path, scenario_name: str = "default",
          mode: str = "full", backup: bool = True) -> dict[str, Any]:
    if mode not in ("full", "ai_only"):
        raise Invalid("mode must be 'full' or 'ai_only'")
    scenario = load_scenario(scenario_dir, scenario_name)
    backup_path: Optional[Path] = write_backup(store, backup_dir, f"before_{mode}_reset") if backup else None
    conn = store.connect()
    try:
        with write_tx(conn):
            if mode == "full":
                for t in ALL_TABLES:
                    conn.execute(f"DELETE FROM {t}")
                _seed_values(store, conn, scenario)
                ts = now_iso()
                _ensure_default_crosshair_profile(store, conn, ts)
                for p in scenario.get("preferences", []):
                    conn.execute(
                        "INSERT INTO preferences(id, dimension, direction, scope, session_id, game, origin_game, source, note, active, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,1,?,?)",
                        (new_id("pref"), p["dimension"], p.get("direction", "prioritize"), p.get("scope", "durable"), None,
                         p.get("game"), p.get("originGame"), p.get("source", "seed"), p.get("note"), ts, ts))
                for e in scenario.get("evidence", []):
                    conn.execute(
                        "INSERT INTO evidence(id, kind, dimension, game, setting_id, proposal_id, detail, session_id, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (new_id("ev"), e["kind"], e.get("dimension"), e.get("game"), e.get("settingId"), None,
                         e.get("detail"), None, e.get("createdAt", ts)))
                for pf in scenario.get("personalFacts", []):
                    conn.execute(
                        "INSERT INTO personal_setup_facts(id, fact_key, label, value_text, origin_game, source_setting_id, "
                        "source, note, active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                        (new_id("fact"), pf["factKey"], pf["label"], pf["valueText"], pf.get("originGame"),
                         pf.get("sourceSettingId"), pf.get("source", "seed"), pf.get("note"), ts, ts),
                    )
                for table, key in (("pins", "pins"), ("locks", "locks")):
                    for game, ids in scenario.get(key, {}).items():
                        for sid in ids:
                            store.require_setting(game, sid)
                            conn.execute(f"INSERT INTO {table}(game, setting_id, created_at) VALUES (?,?,?)", (game, sid, ts))
            else:
                for t in AI_TABLES:
                    conn.execute(f"DELETE FROM {t}")
                conn.execute("DELETE FROM preferences WHERE scope = 'session'")
            sess_cfg = scenario.get("session", {})
            old = store.kv_get(conn, "session") or {}
            session = {
                "sessionId": new_id("ses"),
                "condition": sess_cfg.get("condition", old.get("condition", "baseline") if mode == "ai_only" else "baseline"),
                "selectedGame": sess_cfg.get("selectedGame", "valorant"),
                "adaptationEnabled": sess_cfg.get("adaptationEnabled", True),
                "aiMode": old.get("aiMode", sess_cfg.get("aiMode", "local")) if mode == "ai_only" else sess_cfg.get("aiMode", "local"),
                "scenario": scenario["name"],
                "hardware": {**DEFAULT_HARDWARE, **scenario.get("hardware", {})},
                "startedAt": now_iso(),
            }
            store.kv_set(conn, "session", session)
        return {"scenario": scenario["name"], "mode": mode, "backup": str(backup_path) if backup_path else None,
                "session": session}
    finally:
        conn.close()


def ensure_seeded(store: Store, scenario_dir: Path, backup_dir: Path) -> bool:
    """Seed the default scenario on first run (empty database) and sync any new catalog settings."""
    conn = store.connect()
    try:
        empty = conn.execute("SELECT COUNT(*) AS n FROM setting_values").fetchone()["n"] == 0
    finally:
        conn.close()
    if empty:
        reset(store, scenario_dir, backup_dir, "default", "full", backup=False)
    else:
        sync_catalog_defaults(store)
    return empty
