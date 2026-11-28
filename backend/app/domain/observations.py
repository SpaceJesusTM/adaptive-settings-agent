"""Observation and evidence provenance helpers across VALORANT and CS2.

Separates four epistemic tiers without ever conflating defaults with user intent:
1. Automatically observed configuration (current simulated values & history)
2. Tentatively inferred behavioral patterns (manual edits aligned with a dimension)
3. Explicitly confirmed preferences / remembered facts (authoritative user intent)
4. Consequential setting changes (always initiated or applied by the user)
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..catalog.schema import DIMENSION_LABELS
from .db import loads
from .values import display_value, values_equal

GAME_NAMES = {"valorant": "VALORANT", "cs2": "CS2"}

FACT_SETTING_MAP: dict[str, dict[str, str]] = {
    "mouse_sensitivity": {"valorant": "val.general.sensitivity_aim", "cs2": "cs2.kbmouse.mouse_sensitivity"},
    "push_to_talk_key": {"valorant": "val.controls.key_team_ptt", "cs2": "cs2.kbmouse.key_mic"},
    "voice_activation": {"valorant": "val.audio.party_voice_activation", "cs2": "cs2.audio.voice_mode"},
    "ping_key": {"valorant": "val.controls.key_ping", "cs2": "cs2.kbmouse.key_player_ping"},
    "crouch_walk_convention": {"valorant": "val.controls.key_crouch", "cs2": "cs2.kbmouse.duck_mode"},
    "crosshair_style": {"valorant": "val.crosshair.primary_color", "cs2": "cs2.crosshair.xhair_style"},
}

ONBOARDING_OBSERVATION_SPECS: list[dict[str, Any]] = [
    {
        "key": "mouse_sensitivity",
        "factKey": "mouse_sensitivity",
        "dimension": "comfort",
        "valorantId": "val.general.sensitivity_aim",
        "cs2Id": "cs2.kbmouse.mouse_sensitivity",
        "checkSuffix": "sens",
    },
    {
        "key": "push_to_talk_key",
        "factKey": "push_to_talk_key",
        "dimension": "communication",
        "valorantId": "val.controls.key_team_ptt",
        "cs2Id": "cs2.kbmouse.key_mic",
        "checkSuffix": "ptt",
    },
    {
        "key": "ping_key",
        "factKey": "ping_key",
        "dimension": "communication",
        "valorantId": "val.controls.key_ping",
        "cs2Id": "cs2.kbmouse.key_player_ping",
        "checkSuffix": "ping",
    },
]


def _values_match_text(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) <= 0.005
    except (TypeError, ValueError):
        return str(a or "").strip().lower() == str(b or "").strip().lower()


def observe_setting(store, conn: sqlite3.Connection, game: str, setting_id: str) -> Optional[dict[str, Any]]:
    """Inspect a live setting alongside its origin provenance (manual, AI-applied, scenario seed, or default)."""
    s = store.registry.setting(game, setting_id)
    if s is None:
        return None
    vals = store.flat_values(conn, game)
    cur = vals.get(setting_id)
    cur_disp = display_value(s, cur)

    latest = conn.execute(
        "SELECT b.id AS batch_id, b.source AS source, b.created_at AS created_at "
        "FROM change_events e JOIN change_batches b ON b.id = e.batch_id "
        "WHERE b.game = ? AND e.setting_id = ? AND b.source != 'reset' AND b.undone_by_batch_id IS NULL "
        "ORDER BY b.created_at DESC, b.rowid DESC LIMIT 1",
        (game, setting_id),
    ).fetchone()

    sess = store.session(conn)
    scenario_name = sess.get("scenario")

    if latest is not None:
        src = latest["source"]
        if src in ("manual", "manual_batch", "preset"):
            kind = "user_manual"
            label = "Set manually by you"
            deliberate = True
        elif src == "undo":
            kind = "undo"
            label = "Restored via Undo"
            deliberate = True
        elif src in ("ai_applied", "fallback_applied", "rule_applied", "history_applied"):
            kind = src
            label = "Applied by you from suggestion"
            deliberate = True
        else:
            kind = src
            label = "Updated in session"
            deliberate = True
        batch_id = latest["batch_id"]
        updated_at = latest["created_at"]
    else:
        batch_id = None
        updated_at = None
        if not values_equal(cur, s.sampleInitialValue) and scenario_name not in (None, "default"):
            kind = "scenario_seed"
            label = f"Scenario preset ({scenario_name})"
            deliberate = False
        elif scenario_name in ("valorant_onboarding_to_cs2", "valorant_history_new_cs2") and game == "valorant":
            # Seeded scenario may explicitly set values that happen to match sampleInitialValue (e.g., 0.35)
            kind = "scenario_seed"
            label = f"Scenario configuration ({scenario_name})"
            deliberate = False
        else:
            kind = "default"
            label = "Current simulator default"
            deliberate = False

    return {
        "settingId": s.id,
        "game": game,
        "label": s.exactLabel,
        "path": s.canonicalPath,
        "controlType": s.controlType,
        "value": cur,
        "display": cur_disp,
        "sourceKind": kind,
        "sourceLabel": label,
        "deliberate": deliberate,
        "batchId": batch_id,
        "updatedAt": updated_at,
        "matchesDefault": values_equal(cur, s.sampleInitialValue),
    }


def detect_fact_discrepancies(store, profile, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return mismatches where a remembered personal fact disagrees with live settings in that game."""
    facts = profile.personal_facts(conn)
    discrepancies: list[dict[str, Any]] = []
    for f in facts:
        fk = f["factKey"]
        origin_game = f.get("originGame")
        if not origin_game or fk not in FACT_SETTING_MAP or (fk == "crosshair_style" and not f["sourceSettingId"]):
            continue
        sid = FACT_SETTING_MAP[fk].get(origin_game)
        if not sid:
            continue
        obs = observe_setting(store, conn, origin_game, sid)
        if obs is None:
            continue
        if not _values_match_text(f["valueText"], obs["value"]) and not _values_match_text(f["valueText"], obs["display"]):
            gname = GAME_NAMES.get(origin_game, origin_game)
            discrepancies.append({
                "factId": f["id"],
                "factKey": fk,
                "label": f["label"],
                "savedValue": f["valueText"],
                "game": origin_game,
                "settingId": sid,
                "settingLabel": obs["label"],
                "liveValue": obs["value"],
                "liveDisplay": obs["display"],
                "liveSourceKind": obs["sourceKind"],
                "explanation": (
                    f"You previously saved {f['valueText']} as your preferred {gname} {f['label'].lower()}, "
                    f"but your current {gname} {obs['label']} is {obs['display']}."
                ),
            })
    return discrepancies


def build_observed_summary(store, profile, conn: sqlite3.Connection, current_game: str) -> dict[str, Any]:
    """Build a concise, epistemically honest 'What I've noticed' snapshot for UI and model context."""
    other_game = "valorant" if current_game == "cs2" else "cs2"
    key_settings: list[dict[str, Any]] = []

    for spec in ONBOARDING_OBSERVATION_SPECS:
        src_sid = spec["valorantId"] if other_game == "valorant" else spec["cs2Id"]
        tgt_sid = spec["valorantId"] if current_game == "valorant" else spec["cs2Id"]
        src_obs = observe_setting(store, conn, other_game, src_sid)
        tgt_obs = observe_setting(store, conn, current_game, tgt_sid)
        if src_obs:
            key_settings.append(src_obs)
        if tgt_obs and (tgt_obs["deliberate"] or not src_obs or not _values_match_text(tgt_obs["display"], src_obs["display"])):
            key_settings.append(tgt_obs)

    sess = store.session(conn)
    batches = conn.execute(
        "SELECT id, game, source, label, created_at FROM change_batches "
        "WHERE session_id = ? AND source != 'reset' AND undone_by_batch_id IS NULL "
        "ORDER BY created_at DESC, rowid DESC LIMIT 6",
        (sess["sessionId"],),
    ).fetchall()

    recent_actions: list[dict[str, Any]] = []
    dim_manual_hits: dict[str, list[str]] = {}
    for b in batches:
        evs = conn.execute(
            "SELECT setting_id, new_value_json FROM change_events WHERE batch_id = ?",
            (b["id"],),
        ).fetchall()
        labels: list[str] = []
        for e in evs:
            s = store.registry.setting(b["game"], e["setting_id"])
            if not s:
                continue
            labels.append(s.exactLabel)
            if b["source"] in ("manual", "manual_batch"):
                new_val = loads(e["new_value_json"])
                for h in s.goalHints:
                    if any(values_equal(new_val, v) for v in h.prefer):
                        dim_manual_hits.setdefault(h.dimension, []).append(s.exactLabel)
        recent_actions.append({
            "batchId": b["id"],
            "game": b["game"],
            "source": b["source"],
            "label": b["label"] or ", ".join(labels[:3]) or "Setting update",
            "count": len(evs),
            "createdAt": b["created_at"],
            "summary": (
                f"{'You changed' if b['source'] in ('manual', 'manual_batch', 'preset') else 'You applied'} "
                f"{b['label'] or ', '.join(labels[:2])} in {GAME_NAMES.get(b['game'], b['game'])}"
            ),
        })

    active_pref_dims = {p["dimension"] for p in profile.preferences(conn)}
    tentative_signals: list[dict[str, Any]] = []
    for dim, setting_labels in dim_manual_hits.items():
        if dim in active_pref_dims:
            continue
        uniq = list(dict.fromkeys(setting_labels))
        if uniq:
            tentative_signals.append({
                "dimension": dim,
                "dimensionLabel": DIMENSION_LABELS.get(dim, dim),
                "tentative": True,
                "explanation": (
                    f"Tentative pattern (not saved as a lasting priority): you manually changed {', '.join(uniq[:2])}, "
                    f"which often aligns with {DIMENSION_LABELS.get(dim, dim)}."
                ),
            })

    discrepancies = detect_fact_discrepancies(store, profile, conn)
    return {
        "keySettings": key_settings[:6],
        "recentActions": recent_actions[:4],
        "tentativeSignals": tentative_signals[:2],
        "discrepancies": discrepancies,
    }
