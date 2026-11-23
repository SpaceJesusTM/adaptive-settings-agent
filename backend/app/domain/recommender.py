"""Deterministic, inspectable 4-trigger proactive Discover & cross-game onboarding engine.

Supports four complementary proactive triggers without ever silently applying settings:
1. Context events (simulated performance/audio/network/ranked conditions)
2. Companion configuration follow-ups after recent manual or applied changes
3. Adaptive first-time onboarding (Scenario 1 confirmed personal facts, Scenario 2 durable
   priorities only, Scenario 3 minimal neutral start, Scenario 4 persistent completion/dismissal)
4. Goal & preference ranking (`rank_candidates`) with hold rule & explicit dismissal suppression.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any, Optional

from ..catalog.schema import DIMENSION_LABELS, Setting
from .cross_game import convert_hipfire_sensitivity
from .db import dumps, loads, new_id, now_iso, write_tx
from .errors import Invalid
from .observations import ONBOARDING_OBSERVATION_SPECS, detect_fact_discrepancies, observe_setting
from .profile import ProfileService
from .store import Store
from .values import availability_problem, display_value, values_equal

MAX_RELEVANT_NOW = 4
MAX_GOAL_CANDIDATES = 4
BASIS_FACTOR = {"official": 1.0, "editorial": 0.8}

TRIGGER_LABELS: dict[str, str] = {
    "context_event": "Responding to a simulated event",
    "followup": "Worth checking after your recent change",
    "onboarding": "Getting started",
    "goal_or_preference": "Relevant to your goals & preferences",
}

FOLLOWUP_RULES: list[dict[str, Any]] = [
    {
        "id": "val_vsync_off_check_reflex",
        "game": "valorant",
        "triggerSettingId": "val.video.vsync",
        "triggerValues": ["off"],
        "targetSettingId": "val.video.nvidia_reflex",
        "targetValue": "on_boost",
        "kind": "change",
        "dimension": "input_latency",
        "why": "Since you disabled VSync, enabling NVIDIA Reflex Low Latency can keep render queueing low when GPU-bound.",
    },
    {
        "id": "cs2_vsync_off_check_reflex",
        "game": "cs2",
        "triggerSettingId": "cs2.video.vsync",
        "triggerValues": ["0"],
        "targetSettingId": "cs2.video.nvidia_reflex",
        "targetValue": "1",
        "kind": "change",
        "dimension": "input_latency",
        "why": "With V-Sync disabled, checking NVIDIA Reflex Low Latency helps minimize render-queue latency.",
    },
    {
        "id": "val_hrtf_on_check_stereo",
        "game": "valorant",
        "triggerSettingId": "val.audio.enable_hrtf",
        "triggerValues": ["on"],
        "targetSettingId": "val.audio.speaker_configuration",
        "targetValue": "stereo",
        "kind": "change",
        "dimension": "audio_awareness",
        "why": "HRTF positional cues assume Stereo headphone output rather than Mono.",
    },
    {
        "id": "val_display_fullscreen_check_fps",
        "game": "valorant",
        "triggerSettingId": "val.video.display_mode",
        "triggerValues": ["fullscreen"],
        "targetSettingId": "val.video.limit_fps_always",
        "targetValue": "off",
        "kind": "change",
        "dimension": "performance",
        "why": "In Exclusive Fullscreen, check Limit FPS Always so frame pacing stays responsive for your display.",
    },
    {
        "id": "cs2_ptt_check_mic_key",
        "game": "cs2",
        "triggerSettingId": "cs2.audio.voice_mode",
        "triggerValues": ["1"],
        "targetSettingId": "cs2.kbmouse.key_mic",
        "targetValue": None,
        "kind": "inspect",
        "dimension": "communication",
        "why": "Since Voice Mode is Push to Use Mic, double-check that Use Microphone is bound to a comfortable key.",
    },
    {
        "id": "val_xhair_custom_color",
        "game": "valorant",
        "triggerSettingId": "val.crosshair.primary_color",
        "triggerValues": ["custom"],
        "targetSettingId": "val.crosshair.primary_custom_color",
        "targetValue": None,
        "kind": "inspect",
        "dimension": "visibility",
        "why": "Crosshair Color is set to Custom — confirm your hex color sits cleanly against bright and dark map backgrounds.",
    },
]


def _first_valid_target(setting: Setting, prefer: list[Any], current: Any) -> Any:
    for v in prefer:
        if not values_equal(v, current):
            return v
    return None


def _dismissal_signature(weights: dict[str, dict[str, Any]], extra: str = "") -> str:
    base = ProfileService.signature(weights)
    if not extra:
        return base
    return hashlib.sha1(f"{base}:{extra}".encode()).hexdigest()[:12]


def rank_candidates(
    store: Store,
    profile: ProfileService,
    conn: sqlite3.Connection,
    game: str,
    *,
    weights: Optional[dict[str, dict[str, Any]]] = None,
    limit: int = 10,
    exclude_dismissed: bool = True,
    exclude_staged: bool = True,
) -> list[dict[str, Any]]:
    weights = weights if weights is not None else profile.dimension_weights(conn, game)
    positive = {d: w for d, w in weights.items() if w["weight"] > 0}
    if not positive:
        return []
    values = store.flat_values(conn, game)
    locked = set(store.locks(conn, game))
    hardware = store.hardware(conn)
    staged = {
        r["setting_id"]
        for r in conn.execute(
            "SELECT i.setting_id FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
            "WHERE p.game = ? AND p.status = 'pending' AND i.status = 'pending'",
            (game,),
        )
    } if exclude_staged else set()
    signature = ProfileService.signature(weights)
    dismissed = {
        r["setting_id"]
        for r in conn.execute(
            "SELECT setting_id FROM dismissals WHERE game = ? AND signature = ?",
            (game, signature),
        )
    } if exclude_dismissed else set()

    out: list[dict[str, Any]] = []
    for s in store.registry.settings(game):
        if not s.aiProposable or s.controlType in ("keybind", "preset") or not s.goalHints:
            continue
        if s.id in locked or s.id in staged or s.id in dismissed:
            continue
        if availability_problem(store.registry, s, values, hardware):
            continue
        current = values.get(s.id)
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
                best_score += w
        if best_score <= 0:
            continue
        reasons = weights[best_hint.dimension]["reasons"]
        has_ctx = any(r.get("kind") == "context" for r in reasons)
        trigger_group = "context_event" if has_ctx else "goal_or_preference"
        out.append({
            "kind": "change",
            "triggerGroup": trigger_group,
            "triggerLabel": TRIGGER_LABELS[trigger_group],
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
            "whyOrigin": "goal_hint",
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


def detect_followup_cards(
    store: Store,
    profile: ProfileService,
    conn: sqlite3.Connection,
    game: str,
    *,
    exclude_dismissed: bool = True,
) -> list[dict[str, Any]]:
    """Build low-noise companion follow-up cards after meaningful active-session changes."""
    values = store.flat_values(conn, game)
    locked = set(store.locks(conn, game))
    hardware = store.hardware(conn)
    sess_id = store.session(conn)["sessionId"]
    staged = {
        r["setting_id"]
        for r in conn.execute(
            "SELECT i.setting_id FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
            "WHERE p.game = ? AND p.status = 'pending' AND i.status = 'pending'",
            (game,),
        )
    }
    batches = conn.execute(
        "SELECT id, source, created_at FROM change_batches "
        "WHERE game = ? AND session_id = ? AND source != 'reset' AND undone_by_batch_id IS NULL "
        "ORDER BY created_at DESC, rowid DESC LIMIT 8",
        (game, sess_id),
    ).fetchall()
    if not batches:
        return []

    changed_recently: dict[str, tuple[str, str, str]] = {}
    for b in batches:
        evs = conn.execute(
            "SELECT setting_id, new_value_json FROM change_events WHERE batch_id = ?",
            (b["id"],),
        ).fetchall()
        for e in evs:
            if e["setting_id"] not in changed_recently:
                changed_recently[e["setting_id"]] = (b["created_at"], str(loads(e["new_value_json"])), b["id"])

    weights = profile.dimension_weights(conn, game)
    sig = ProfileService.signature(weights)
    dismissed = {
        r["setting_id"]
        for r in conn.execute(
            "SELECT setting_id FROM dismissals WHERE game = ? AND signature = ?",
            (game, sig),
        )
    } if exclude_dismissed else set()

    resolved_followups = {
        (r["rule_id"], r["trigger_batch_id"])
        for r in conn.execute(
            "SELECT rule_id, trigger_batch_id FROM followup_resolutions WHERE game = ?",
            (game,),
        )
    } if exclude_dismissed else set()

    cards: list[dict[str, Any]] = []
    for rule in FOLLOWUP_RULES:
        if rule["game"] != game:
            continue
        trig_id = rule["triggerSettingId"]
        if trig_id not in changed_recently:
            continue
        cur_trig = values.get(trig_id)
        if not any(values_equal(cur_trig, tv) for tv in rule["triggerValues"]):
            continue
        trig_time, _, trig_batch_id = changed_recently[trig_id]
        if (rule["id"], trig_batch_id) in resolved_followups:
            continue
        target_id = rule["targetSettingId"]
        # Suppress follow-up if the user already adjusted the companion setting at/after the trigger change
        if target_id in changed_recently and changed_recently[target_id][0] >= trig_time:
            continue
        s_trig = store.registry.setting(game, trig_id)
        s_tgt = store.registry.setting(game, target_id)
        if s_trig is None or s_tgt is None:
            continue
        if target_id in locked or target_id in staged or target_id in dismissed:
            continue
        if availability_problem(store.registry, s_tgt, values, hardware):
            continue
        cur_tgt = values.get(target_id)
        if rule["kind"] == "change":
            if values_equal(cur_tgt, rule["targetValue"]):
                continue
            target_disp = display_value(s_tgt, rule["targetValue"])
        else:
            target_disp = "Manual review"

        cards.append({
            "kind": rule["kind"],
            "triggerGroup": "followup",
            "triggerLabel": TRIGGER_LABELS["followup"],
            "ruleId": rule["id"],
            "triggerBatchId": trig_batch_id,
            "settingId": s_tgt.id,
            "label": s_tgt.exactLabel,
            "path": s_tgt.canonicalPath,
            "currentValue": cur_tgt,
            "currentDisplay": display_value(s_tgt, cur_tgt),
            "targetValue": rule["targetValue"] if rule["kind"] == "change" else cur_tgt,
            "targetDisplay": target_disp,
            "score": 1.25,
            "dimension": rule["dimension"],
            "dimensionLabel": DIMENSION_LABELS.get(rule["dimension"], rule["dimension"]),
            "whatItDoes": s_tgt.description,
            "whatItDoesSource": s_tgt.descriptionSource,
            "why": rule["why"],
            "whyOrigin": "followup_rule",
            "whyBasis": "editorial",
            "basedOn": [f"your recent change to {s_trig.exactLabel} ({display_value(s_trig, cur_trig)})"],
            "crossGame": False,
            "tradeoff": s_tgt.riskOrTradeoffs,
            "sourceURL": s_tgt.sourceURL,
            "verificationStatus": s_tgt.verificationStatus,
            "order": s_tgt.order,
        })
    return cards[:2]


def build_onboarding_cards(
    store: Store,
    profile: ProfileService,
    conn: sqlite3.Connection,
    game: str,
    *,
    has_priority_recs: Optional[bool] = None,
) -> list[dict[str, Any]]:
    """Build evidence-sensitive onboarding cards from live observations, facts, and discrepancies.

    Never claims defaults or scenario seeds represent personal user preferences, and never suppresses
    relevant onboarding checks solely because unrelated dimension priorities exist.
    """
    ob = profile.ensure_onboarding_tx(conn, game)
    if ob["status"] in ("completed", "dismissed"):
        return []

    done_checks = set(ob["completedChecks"]) | set(ob["dismissedChecks"])
    other_game = "valorant" if game == "cs2" else "cs2"
    facts = profile.personal_facts(conn)
    other_facts = {f["factKey"]: f for f in facts if f.get("originGame") == other_game}
    same_facts = {f["factKey"]: f for f in facts if f.get("originGame") == game}
    discrepancies = detect_fact_discrepancies(store, profile, conn)
    disc_by_key = {(d["game"], d["factKey"]): d for d in discrepancies}
    values = store.flat_values(conn, game)

    if has_priority_recs is None:
        has_priority_recs = bool(profile.preferences(conn) or profile.session_goals(conn, game))

    title_game = "CS2" if game == "cs2" else "VALORANT"
    other_title = "VALORANT" if other_game == "valorant" else "CS2"
    cards: list[dict[str, Any]] = []

    def make_inspect(
        setting_id: str,
        check_id: str,
        why: str,
        based_on: list[str],
        dim: str,
        score: float,
        caveat: Optional[str] = None,
        cross_game: bool = False,
    ) -> Optional[dict[str, Any]]:
        if check_id in done_checks:
            return None
        s = store.registry.setting(game, setting_id)
        if s is None:
            return None
        cur = values.get(s.id)
        return {
            "kind": "inspect",
            "triggerGroup": "onboarding",
            "triggerLabel": f"Getting started in {title_game}",
            "checkId": check_id,
            "settingId": s.id,
            "label": s.exactLabel,
            "path": s.canonicalPath,
            "currentValue": cur,
            "currentDisplay": display_value(s, cur),
            "targetValue": cur,
            "targetDisplay": "Manual check",
            "score": score,
            "dimension": dim,
            "dimensionLabel": DIMENSION_LABELS.get(dim, dim),
            "whatItDoes": s.description,
            "whatItDoesSource": s.descriptionSource,
            "why": why,
            "whyOrigin": "onboarding_observation",
            "whyBasis": "official",
            "basedOn": based_on,
            "crossGame": cross_game,
            "tradeoff": caveat or s.riskOrTradeoffs,
            "sourceURL": s.sourceURL,
            "verificationStatus": s.verificationStatus,
            "order": s.order,
        }

    for spec in ONBOARDING_OBSERVATION_SPECS:
        fk = spec["factKey"]
        dim = spec["dimension"]
        check_id = f"ob_{game}_{spec['checkSuffix']}"
        cur_sid = spec["cs2Id"] if game == "cs2" else spec["valorantId"]
        other_sid = spec["valorantId"] if game == "cs2" else spec["cs2Id"]
        cur_obs = observe_setting(store, conn, game, cur_sid)
        other_obs = observe_setting(store, conn, other_game, other_sid)
        other_fact = other_facts.get(fk)
        same_fact = same_facts.get(fk)
        other_disc = disc_by_key.get((other_game, fk))
        same_disc = disc_by_key.get((game, fk))
        if cur_obs is None:
            continue

        if fk == "mouse_sensitivity":
            if other_disc and other_obs:
                conv = convert_hipfire_sensitivity(other_game, game, str(other_obs["value"]), confirmed=other_obs["deliberate"])
                conv_note = (
                    f" Using your live {other_title} value ({other_obs['display']}), a 360° hipfire match is ~{conv['convertedValue']} ({conv['formula']})."
                    if conv.get("convertible")
                    else ""
                )
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"Your remembered profile lists {other_title} sensitivity as {other_fact['valueText']}, "
                        f"while live {other_title} currently has {other_obs['display']} ({other_obs['sourceLabel']}).{conv_note} "
                        f"Inspect {title_game}'s slider manually so you convert from the one you actually use."
                    ),
                    [
                        f"remembered {other_title} note ({other_fact['valueText']})",
                        f"live {other_title} setting ({other_obs['display']} — {other_obs['sourceLabel']})",
                    ],
                    dim,
                    1.26,
                    " ".join(conv.get("caveats", [])) or "Key/sensitivity conversions never modify values automatically.",
                    cross_game=True,
                )
            elif other_fact:
                conv = convert_hipfire_sensitivity(other_game, game, other_fact["valueText"], confirmed=True)
                if conv.get("convertible"):
                    why = (
                        f"Based on your remembered {other_title} sensitivity ({conv['sourceValue']}), "
                        f"a 360° hipfire match in {title_game} is around {conv['convertedValue']} ({conv['formula']})."
                    )
                    caveat = " ".join(conv["caveats"])
                else:
                    why = (
                        f"You recorded a {other_title} sensitivity note ({other_fact['valueText']}). "
                        f"Inspect {title_game}'s sensitivity slider directly to dial in your aiming feel."
                    )
                    caveat = "Requires identical mouse DPI and comfort testing in practice range."
                c = make_inspect(
                    cur_sid,
                    check_id,
                    why,
                    [f"your remembered {other_title} sensitivity ({other_fact['valueText']})"],
                    dim,
                    1.24,
                    caveat,
                    cross_game=True,
                )
            elif other_obs and other_obs["deliberate"]:
                conv = convert_hipfire_sensitivity(other_game, game, str(other_obs["value"]), confirmed=True)
                conv_str = f" (approx. {conv['convertedValue']} in {title_game}, {conv['formula']})" if conv.get("convertible") else ""
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"Your live {other_title} sensitivity is {other_obs['display']} ({other_obs['sourceLabel']}){conv_str}. "
                        f"Inspect {title_game}'s current {cur_obs['display']} slider manually if you want a matching turn distance."
                    ),
                    [f"observed {other_title} edit ({other_obs['display']} — {other_obs['sourceLabel']})"],
                    dim,
                    1.21,
                    " ".join(conv.get("caveats", [])) or "Assumes identical mouse DPI.",
                    cross_game=True,
                )
            elif same_disc:
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"Your remembered {title_game} sensitivity ({same_fact['valueText']}) differs from "
                        f"live {title_game} ({cur_obs['display']} — {cur_obs['sourceLabel']}). Confirm which value you want to keep."
                    ),
                    [f"remembered {title_game} note ({same_fact['valueText']})", f"live {title_game} ({cur_obs['display']})"],
                    dim,
                    1.22,
                    "Sensitivity sliders stay under manual user control.",
                )
            elif cur_obs["deliberate"]:
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"You set {title_game}'s Mouse Sensitivity to {cur_obs['display']} ({cur_obs['sourceLabel']}). "
                        f"Mark this checked once you're happy with your turn feel."
                    ),
                    [f"your recent edit in {title_game} ({cur_obs['display']})"],
                    dim,
                    1.05,
                )
            elif other_obs and other_obs["sourceKind"] == "scenario_seed":
                if has_priority_recs:
                    continue
                conv = convert_hipfire_sensitivity(other_game, game, str(other_obs["value"]), confirmed=False)
                ref = f" A 360° hipfire match would be ~{conv['convertedValue']} ({conv['formula']}), though that preset was not confirmed as your preference." if conv.get("convertible") else ""
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"The loaded scenario sets {other_title} sensitivity to {other_obs['display']} (scenario preset, not yet confirmed as your personal preference).{ref} "
                        f"Check whether {title_game}'s {cur_obs['display']} suits your mouse DPI."
                    ),
                    [f"observed scenario preset in {other_title} ({other_obs['display']})"],
                    dim,
                    1.15,
                    "Scenario values are unconfirmed starting points; adjust sensitivity manually.",
                    cross_game=True,
                )
            else:
                if has_priority_recs:
                    continue
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"{title_game} Mouse Sensitivity is currently {cur_obs['display']} ({cur_obs['sourceLabel']}). "
                        f"Confirm it fits your mouse DPI and wrist/arm space — no personal preference is assumed yet."
                    ),
                    [f"observed {title_game} setting ({cur_obs['display']} — {cur_obs['sourceLabel']})"],
                    dim,
                    1.14,
                )
            if c:
                cards.append(c)
            continue

        if fk == "push_to_talk_key":
            if other_disc and other_obs:
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"Your remembered {other_title} Push-to-Talk key is {other_fact['valueText']}, while live {other_title} "
                        f"uses {other_obs['display']} ({other_obs['sourceLabel']}). Inspect {title_game}'s {cur_obs['display']} keybind manually."
                    ),
                    [f"remembered {other_title} PTT ({other_fact['valueText']})", f"live {other_title} ({other_obs['display']})"],
                    dim,
                    1.24,
                    "Keybindings are personal ergonomics and never copied automatically.",
                    cross_game=True,
                )
            elif other_fact:
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"You asked to remember {other_fact['valueText']} for Push-to-Talk in {other_title}. "
                        f"Inspect {title_game}'s voice key (currently {cur_obs['display']}) and rebind manually if you want the same muscle memory."
                    ),
                    [f"your remembered {other_title} push-to-talk key ({other_fact['valueText']})"],
                    dim,
                    1.22,
                    "Keybindings are personal ergonomics and are never copied automatically.",
                    cross_game=True,
                )
            elif other_obs and other_obs["deliberate"]:
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"Your live {other_title} voice key is set to {other_obs['display']} ({other_obs['sourceLabel']}). "
                        f"Check whether {title_game}'s {cur_obs['display']} feels natural without overriding muscle memory."
                    ),
                    [f"observed {other_title} edit ({other_obs['display']} — {other_obs['sourceLabel']})"],
                    dim,
                    1.19,
                    "Keybindings stay under manual user control.",
                    cross_game=True,
                )
            elif other_obs and other_obs["sourceKind"] == "scenario_seed":
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"The loaded scenario binds {other_title} voice to {other_obs['display']} (scenario preset, not confirmed as your preference). "
                        f"Check {title_game}'s {cur_obs['display']} keybind directly."
                    ),
                    [f"observed scenario preset in {other_title} ({other_obs['display']})"],
                    dim,
                    1.14,
                    "Keybindings stay under manual user control.",
                    cross_game=True,
                )
            else:
                c = make_inspect(
                    cur_sid,
                    check_id,
                    (
                        f"{title_game} Push-to-Talk is currently bound to {cur_obs['display']} ({cur_obs['sourceLabel']}). "
                        f"Confirm this key feels comfortable before queueing; no saved voice preference is assumed."
                    ),
                    [f"observed {title_game} setting ({cur_obs['display']} — {cur_obs['sourceLabel']})"],
                    dim,
                    1.12,
                )
            if c:
                cards.append(c)
            continue

        if fk == "ping_key":
            has_ping_signal = bool(other_fact or other_disc or same_disc or (other_obs and other_obs["deliberate"]))
            if not has_ping_signal:
                continue
            if other_disc and other_obs:
                why = (
                    f"Your remembered {other_title} ping key is {other_fact['valueText']}, while live {other_title} is bound to {other_obs['display']}. "
                    f"Check whether {title_game}'s {cur_obs['display']} ping key matches your habit."
                )
                based = [f"remembered {other_title} ping ({other_fact['valueText']})", f"live {other_title} ({other_obs['display']})"]
            elif other_fact:
                why = (
                    f"You remembered {other_fact['valueText']} for callout pings in {other_title}. "
                    f"Check whether {title_game}'s ping key ({cur_obs['display']}) matches what feels natural."
                )
                based = [f"your remembered {other_title} ping key ({other_fact['valueText']})"]
            elif other_obs and other_obs["deliberate"]:
                why = (
                    f"Your live {other_title} ping key is set to {other_obs['display']} ({other_obs['sourceLabel']}). "
                    f"Inspect {title_game}'s {cur_obs['display']} keybind manually if you use quick callouts."
                )
                based = [f"observed {other_title} edit ({other_obs['display']})"]
            else:
                why = (
                    f"The loaded scenario sets {other_title} ping to {other_obs['display']} (scenario preset). "
                    f"Check {title_game}'s {cur_obs['display']} ping key if you rely on map pings."
                )
                based = [f"observed scenario preset in {other_title} ({other_obs['display']})"]
            c = make_inspect(
                cur_sid,
                check_id,
                why,
                based,
                dim,
                1.18 if (other_fact or other_obs and other_obs["deliberate"]) else 1.11,
                "Keybindings stay under manual user control.",
                cross_game=True,
            )
            if c:
                cards.append(c)

    cards.sort(key=lambda c: (-c["score"], c["order"]))
    return cards


class RelevantNowService:
    def __init__(self, store: Store, profile: ProfileService):
        self.store = store
        self.profile = profile

    def _state_signature(self, conn: sqlite3.Connection, game: str, weights: dict[str, dict[str, Any]]) -> str:
        ob = self.profile.get_onboarding(conn, game)
        fups = detect_followup_cards(self.store, self.profile, conn, game)
        extra = "|".join([
            str(ob.get("status")),
            ",".join(f["settingId"] for f in fups),
            ",".join(f["id"] for f in self.profile.personal_facts(conn)),
            ",".join(d for g in self.profile.session_goals(conn, game) for d in g.get("dimensions", [])),
        ])
        return _dismissal_signature(weights, extra)

    def _card_state(
        self,
        conn: sqlite3.Connection,
        game: str,
        card: dict[str, Any],
        weights: Optional[dict[str, dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        s = self.store.registry.setting(game, card["settingId"])
        state = card.get("state", "suggested")
        if s is None:
            return {**card, "state": "stale"}
        values = self.store.flat_values(conn, game)
        cur = values.get(s.id)
        ob = self.profile.get_onboarding(conn, game)
        weights = weights if weights is not None else self.profile.dimension_weights(conn, game)
        check_id = card.get("checkId")
        if state != "dismissed":
            if card.get("triggerGroup") == "followup":
                rule_id = card.get("ruleId")
                trig_batch_id = card.get("triggerBatchId")
                res_row = (
                    conn.execute(
                        "SELECT status FROM followup_resolutions WHERE game = ? AND rule_id = ? AND trigger_batch_id = ?",
                        (game, rule_id, trig_batch_id),
                    ).fetchone()
                    if rule_id and trig_batch_id
                    else None
                )
                rule_def = next((r for r in FOLLOWUP_RULES if r["id"] == rule_id), None)
                undone_trig = (
                    conn.execute(
                        "SELECT 1 FROM change_batches WHERE id = ? AND undone_by_batch_id IS NOT NULL",
                        (trig_batch_id,),
                    ).fetchone()
                    if trig_batch_id
                    else None
                )
                trig_still_matches = (
                    rule_def is None
                    or any(values_equal(values.get(rule_def["triggerSettingId"]), tv) for tv in rule_def["triggerValues"])
                )
                if res_row:
                    state = "checked" if res_row["status"] == "checked" else "no_longer_relevant"
                elif undone_trig or not trig_still_matches:
                    state = "no_longer_relevant"
                elif card.get("kind") == "change" and values_equal(cur, card["targetValue"]):
                    state = "applied"
                elif card.get("kind") == "change" and self.store.is_locked(conn, game, s.id):
                    state = "locked"
                elif card.get("kind") == "change" and conn.execute(
                    "SELECT 1 FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id WHERE p.game = ? AND "
                    "p.status = 'pending' AND i.status = 'pending' AND i.setting_id = ?",
                    (game, s.id),
                ).fetchone():
                    state = "staged"
                elif not values_equal(cur, card.get("currentValue")):
                    state = "changed"
                else:
                    state = "suggested"
            elif card.get("kind") == "inspect":
                if check_id and check_id in ob.get("completedChecks", []):
                    state = "checked"
                elif not values_equal(cur, card.get("currentValue")):
                    state = "changed"
                else:
                    state = "suggested"
            else:
                dim = card.get("dimension")
                if self.store.is_locked(conn, game, s.id):
                    state = "locked"
                elif values_equal(cur, card["targetValue"]):
                    state = "applied"
                elif conn.execute(
                    "SELECT 1 FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id WHERE p.game = ? AND "
                    "p.status = 'pending' AND i.status = 'pending' AND i.setting_id = ?",
                    (game, s.id),
                ).fetchone():
                    state = "staged"
                elif card.get("triggerGroup") == "goal_or_preference" and dim and weights.get(dim, {}).get("weight", 0.0) <= 0:
                    state = "no_longer_relevant"
                elif not values_equal(cur, card["currentValue"]):
                    state = "changed"
                else:
                    state = "suggested"
        return {**card, "state": state, "liveValue": cur, "liveDisplay": display_value(s, cur)}

    def _collect_candidates(self, conn: sqlite3.Connection, game: str) -> list[dict[str, Any]]:
        weights = self.profile.dimension_weights(conn, game)
        followup_cards = detect_followup_cards(self.store, self.profile, conn, game)
        goal_cards = rank_candidates(self.store, self.profile, conn, game, weights=weights, limit=MAX_RELEVANT_NOW)
        ctx_cards = [c for c in goal_cards if c.get("triggerGroup") == "context_event"]
        non_ctx_goal_cards = [c for c in goal_cards if c.get("triggerGroup") != "context_event"]
        ob_cards = build_onboarding_cards(
            self.store,
            self.profile,
            conn,
            game,
            has_priority_recs=bool(non_ctx_goal_cards),
        )
        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        has_cross_ob = any(c.get("crossGame") for c in ob_cards)
        buckets: tuple[list[dict[str, Any]], ...] = (
            (ctx_cards, followup_cards, ob_cards, non_ctx_goal_cards)
            if has_cross_ob or not non_ctx_goal_cards
            else (ctx_cards, followup_cards, non_ctx_goal_cards[:2], ob_cards[:2], non_ctx_goal_cards[2:], ob_cards[2:])
        )

        for bucket in buckets:
            for c in bucket:
                if c["settingId"] in seen_ids:
                    continue
                seen_ids.add(c["settingId"])
                merged.append(c)
                if len(merged) >= MAX_RELEVANT_NOW:
                    return merged
        return merged

    def get(self, game: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            row = conn.execute("SELECT * FROM relevant_now WHERE game = ?", (game,)).fetchone()
            weights = self.profile.dimension_weights(conn, game)
            ob = self.profile.get_onboarding(conn, game)
            ctx = self.profile.active_context(conn, game)
            fups = detect_followup_cards(self.store, self.profile, conn, game)
            can_revisit = ob.get("status") in ("completed", "dismissed")
            if row is None:
                return {
                    "game": game,
                    "items": [],
                    "trigger": None,
                    "createdAt": None,
                    "updateAvailable": False,
                    "hasEvidence": bool(weights or fups or ob.get("status") == "active"),
                    "context": ctx,
                    "onboardingStatus": ob.get("status"),
                    "canRevisitOnboarding": can_revisit,
                }
            items = [self._card_state(conn, game, c, weights) for c in loads(row["items_json"], [])]
            fresh = self._collect_candidates(conn, game)
            visible = [c["settingId"] for c in items if c["state"] in ("suggested", "changed")]
            fresh_ids = [c["settingId"] for c in fresh]
            cur_sig = self._state_signature(conn, game, weights)
            update_available = bool(fresh_ids) and (
                cur_sig != row["signature"]
                or (len(visible) == 0 and any(f not in [c["settingId"] for c in items] for f in fresh_ids))
            )
            return {
                "game": game,
                "items": items,
                "trigger": row["trigger"],
                "createdAt": row["created_at"],
                "updateAvailable": update_available,
                "hasEvidence": bool(weights or fups or self.profile.personal_facts(conn) or ob.get("status") == "active"),
                "context": ctx,
                "onboardingStatus": ob.get("status"),
                "canRevisitOnboarding": can_revisit,
            }
        finally:
            conn.close()

    def refresh(self, game: str, trigger: str) -> dict[str, Any]:
        if trigger not in (
            "first_visit",
            "context_event",
            "user_refresh",
            "preference_change",
            "onboarding_revisit",
            "followup",
            "goal_change",
            "memory_update",
            "undo",
        ):
            raise Invalid("Unknown refresh trigger")
        conn = self.store.connect()
        try:
            with write_tx(conn):
                weights = self.profile.dimension_weights(conn, game)
                cands = self._collect_candidates(conn, game)
                items = [{**c, "cardId": new_id("card"), "state": "suggested"} for c in cands]
                sig = self._state_signature(conn, game, weights)
                conn.execute(
                    "INSERT INTO relevant_now(game, items_json, signature, trigger, created_at) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(game) DO UPDATE SET items_json = excluded.items_json, signature = excluded.signature, "
                    "trigger = excluded.trigger, created_at = excluded.created_at",
                    (game, dumps(items), sig, trigger, now_iso()),
                )
        finally:
            conn.close()
        return self.get(game)

    def sync_on_event(self, game: str, trigger: str) -> dict[str, Any]:
        """Proactively update Discover on runtime events (goal shift, memory save, manual edit, undo)."""
        return self.refresh(game, trigger)

    def ensure_first_visit(self, game: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            exists = conn.execute("SELECT 1 FROM relevant_now WHERE game = ?", (game,)).fetchone()
        finally:
            conn.close()
        return self.get(game) if exists else self.refresh(game, "first_visit")

    def mark_checked(self, game: str, check_id: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                ob = self.profile.get_onboarding(conn, game)
                if check_id.startswith("ob_"):
                    ob = self.profile.mark_onboarding_check(conn, game, check_id, action="complete")
                row = conn.execute("SELECT items_json FROM relevant_now WHERE game = ?", (game,)).fetchone()
                if row:
                    items = loads(row["items_json"], [])
                    for c in items:
                        matches_ob = c.get("checkId") == check_id
                        matches_fu = c.get("triggerGroup") == "followup" and check_id in (
                            c.get("ruleId"), c.get("settingId"), c.get("cardId")
                        )
                        if matches_ob or matches_fu:
                            c["state"] = "checked"
                            if matches_fu and c.get("ruleId") and c.get("triggerBatchId"):
                                conn.execute(
                                    "INSERT OR REPLACE INTO followup_resolutions(id, game, rule_id, trigger_batch_id, status, created_at) "
                                    "VALUES (?,?,?,?,?,?)",
                                    (new_id("fres"), game, c["ruleId"], c["triggerBatchId"], "checked", now_iso()),
                                )
                    remaining_ob = [
                        c for c in items if c.get("triggerGroup") == "onboarding" and c.get("state") in ("suggested", "changed")
                    ]
                    if not remaining_ob and ob.get("status") == "active" and any(c.get("triggerGroup") == "onboarding" for c in items):
                        self.profile.set_onboarding_status_tx(conn, game, "completed")
                    conn.execute("UPDATE relevant_now SET items_json = ? WHERE game = ?", (dumps(items), game))
        finally:
            conn.close()
        return self.get(game)

    def revisit_onboarding(self, game: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                self.profile.set_onboarding_status_tx(conn, game, "active", clear_dismissed=True)
        finally:
            conn.close()
        return self.refresh(game, "onboarding_revisit")

    def dismiss(self, game: str, setting_id: str, reason: Optional[str]) -> dict[str, Any]:
        s = self.store.require_setting(game, setting_id)
        conn = self.store.connect()
        try:
            with write_tx(conn):
                weights = self.profile.dimension_weights(conn, game)
                sess_id = self.store.session(conn)["sessionId"]
                conn.execute(
                    "INSERT INTO dismissals(id, game, setting_id, reason, signature, session_id, created_at) VALUES (?,?,?,?,?,?,?)",
                    (new_id("dis"), game, setting_id, reason, ProfileService.signature(weights),
                     sess_id, now_iso()),
                )
                row = conn.execute("SELECT items_json FROM relevant_now WHERE game = ?", (game,)).fetchone()
                if row:
                    items = loads(row["items_json"], [])
                    for c in items:
                        if c["settingId"] == setting_id:
                            c["state"] = "dismissed"
                            c["dismissReason"] = reason
                            if c.get("checkId"):
                                self.profile.mark_onboarding_check(conn, game, c["checkId"], action="dismiss")
                            if c.get("triggerGroup") == "followup" and c.get("ruleId") and c.get("triggerBatchId"):
                                conn.execute(
                                    "INSERT OR REPLACE INTO followup_resolutions(id, game, rule_id, trigger_batch_id, status, created_at) "
                                    "VALUES (?,?,?,?,?,?)",
                                    (new_id("fres"), game, c["ruleId"], c["triggerBatchId"], "dismissed", now_iso()),
                                )
                    remaining_ob = [
                        c for c in items if c.get("triggerGroup") == "onboarding" and c.get("state") in ("suggested", "changed")
                    ]
                    if not remaining_ob and self.profile.get_onboarding(conn, game).get("status") == "active":
                        if any(c.get("triggerGroup") == "onboarding" for c in items):
                            self.profile.set_onboarding_status_tx(conn, game, "dismissed")
                    conn.execute("UPDATE relevant_now SET items_json = ? WHERE game = ?", (dumps(items), game))
                dims = [h.dimension for h in s.goalHints if h.dimension in weights]
                for d in dims or [None]:
                    self.profile.add_evidence(
                        conn,
                        kind="dismissed",
                        dimension=d,
                        game=game,
                        setting_id=setting_id,
                        detail=f"Dismissed suggestion for {s.exactLabel}" + (f" ({reason})" if reason else ""),
                    )
        finally:
            conn.close()
        return self.get(game)
