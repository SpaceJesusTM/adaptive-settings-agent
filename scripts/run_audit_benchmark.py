"""Run synthetic GamePlan journeys through the public HTTP API in isolated SQLite DBs.

From any checkout: python scripts/run_audit_benchmark.py --out /tmp/audit.json
To compare revisions, run this same script with --repo pointing to each checkout.
Default runs use the labeled offline fallback. To run the same prompts with Ollama,
set OLLAMA_MODEL in the benchmark process and pass --mode local. The checkout's .env
is ignored. Fixture values and scoring rubrics never enter chat.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

VAL = "valorant"
CS = "cs2"

PILOTS = {
    "a2": {
        "game": VAL,
        "prompt": ("Imagine I am playing casually and want the game to look as visually detailed "
                   "and polished as possible, including richer lighting effects. I am willing to "
                   "sacrifice some FPS for better image quality. Keep my personal controls, "
                   "crosshair, audio settings, resolution and aspect ratio unchanged."),
        # Starting value, full-credit values, half-credit values.
        "criteria": {
            "val.video.material_quality": ("high", ("high",), ("med",)),
            "val.video.texture_quality": ("low", ("high",), ("med",)),
            "val.video.detail_quality": ("low", ("high",), ("med",)),
            "val.video.ui_quality": ("low", ("high",), ("med",)),
            "val.video.anti_aliasing": ("none", ("msaa_4x",), ("msaa_2x",)),
            "val.video.anisotropic_filtering": ("1x", ("16x",), ("8x",)),
            "val.video.bloom": ("on", ("on",), ()),
            "val.video.cast_shadows": ("off", ("on",), ()),
        },
    },
    "b2": {
        "game": CS,
        "prompt": ("Imagine I am playing competitively and want the highest practical frame rate "
                   "and responsive gameplay while keeping enemies clearly visible. Configure the "
                   "graphics and frame-pacing settings accordingly, but keep my personal controls, "
                   "crosshair, audio settings, resolution and aspect ratio unchanged."),
        "criteria": {
            "cs2.video.msaa": ("8", ("0", "cmaa2", "2"), ("4",)),
            "cs2.video.global_shadow_quality": ("2", ("0",), ("1",)),
            "cs2.video.model_texture_detail": ("0", ("0", "1"), ()),
            "cs2.video.shader_detail": ("0", ("0",), ()),
            "cs2.video.particle_detail": ("3", ("0",), ("1",)),
            "cs2.video.ambient_occlusion": ("3", ("0",), ("2",)),
            "cs2.video.vsync": ("1", ("0",), ()),
            "cs2.video.nvidia_reflex": ("0", ("1", "2"), ()),
        },
    },
}

EXACT = {
    VAL: {
        "val.general.rotate": ("rotate", "fixed", "Set minimap rotation to Fixed."),
        "val.video.network_rtt": ("hide", "text", "Set Network RTT to Text Only."),
        "val.audio.overall_volume": (80, 60, "Set Overall Volume to 60%."),
        "val.general.minimap_zoom": (0.9, 0.7, "Set Minimap Zoom to 0.7."),
    },
    CS: {
        "cs2.game.radar_rotating": ("0", "1", "Enable rotating radar."),
        "cs2.game.telemetry_ping": ("0", "2", "Set Show ping to Always."),
        "cs2.audio.master_volume": (0.8, 0.4, "Set Master Volume to 40%."),
        "cs2.video.hud_edge_x": (1.0, 0.85, "Set horizontal HUD Edge Position to 0.85."),
    },
}

# Independently specified content proxies. Manual review of full replies remains necessary.
EXPLANATIONS = (
    ("aa", VAL, "What does anti-aliasing do?", "val.video.anti_aliasing",
     (r"jagg|smooth", r"edg|geometr", r"performance|gpu|frame rate")),
    ("ao", CS, "Explain ambient occlusion.", "cs2.video.ambient_occlusion",
     (r"contact|crevic|corners|nearby", r"light|shad", r"performance|gpu|frame rate")),
    ("af", VAL, "What is anisotropic filtering?", "val.video.anisotropic_filtering",
     (r"texture", r"oblique|angle|distance", r"gpu|performance|frame rate")),
    ("vsync", VAL, "What does VSync do?", "val.video.vsync",
     (r"refresh|synchron", r"tear", r"lag|latency")),
    ("reflex", CS, "Explain NVIDIA Reflex.", "cs2.video.nvidia_reflex",
     (r"input|system latency", r"gpu|power|boost", r"frame|bottleneck")),
    ("shadows", CS, "How does Global Shadow Quality differ from Dynamic Shadows?",
     "cs2.video.global_shadow_quality", (r"global|overall", r"dynamic|player", r"indoors|sun only|light sources")),
    ("fps_hz", CS, "What is the difference between FPS and monitor refresh rate?", None,
     (r"per second|frame rate", r"display|monitor", r"render|produc")),
    ("diagnostic", VAL, "What does Network RTT mean?", "val.video.network_rtt",
     (r"round.trip|latency", r"server", r"network|connect")),
)

VISIBLE = {"suggested", "changed", "new"}


def settings_diff(before, after):
    return {sid: [old, after.get(sid)] for sid, old in before.items() if after.get(sid) != old}


def active_cards(view):
    return [item for item in view["items"] if item["state"] in VISIBLE]


def card_items(cards):
    return [{k: c.get(k) for k in ("settingId", "kind", "targetValue", "why", "basedOn", "triggerGroup", "dimension")}
            for c in cards]


def preference_items(profile):
    return [{k: p.get(k) for k in ("dimension", "direction", "scope", "game", "source")}
            for p in profile["preferences"]]


def goals(profile, game):
    return [goal["dimensions"] for goal in profile["sessionGoals"][game]]


class Scenario:
    def __init__(self, client, mode, group, results, repetition):
        self.client = client
        self.mode = mode
        self.group = group
        self.results = results
        self.repetition = repetition
        self.turns = []

    def request(self, method, path, data=None, *, expected=None):
        kwargs = {} if data is None else {"json": data}
        response = self.client.request(method, "/api" + path, **kwargs)
        if expected is None:
            response.raise_for_status()
        elif response.status_code not in expected:
            raise RuntimeError(f"{method} {path} returned {response.status_code}, expected {expected}")
        return response.json()

    def select(self, game, condition="adaptive"):
        self.request("PUT", "/session", {"selectedGame": game, "condition": condition, "aiMode": self.mode})

    def state(self, game):
        return self.request("GET", f"/games/{game}/state")

    def values(self, game):
        return {sid: data["value"] for sid, data in self.state(game)["values"].items()}

    def profile(self, game):
        return self.request("GET", f"/profile?game={game}")

    def manual(self, game, settings):
        return self.request("POST", f"/games/{game}/batch",
                            {"changes": [{"settingId": sid, "value": value} for sid, value in settings.items()]})

    def discover(self, game):
        return self.request("GET", f"/games/{game}/relevant-now")

    def event(self, game, kind):
        return self.request("POST", "/context-events", {"game": game, "eventType": kind})

    def compare(self, game, query):
        response = self.client.get("/api/cross-game/compare", params={"game": game, "q": query})
        response.raise_for_status()
        return response.json()["comparisons"]

    def turn(self, game, message):
        before = {g: self.values(g) for g in (VAL, CS)}
        started = self.request("POST", "/chat", {"game": game, "message": message, "uiState": {}})
        deadline = time.monotonic() + 200
        while True:
            run = self.request("GET", f"/chat/runs/{started['runId']}")
            if run["status"] != "running":
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Assistant exceeded the benchmark polling deadline")
            time.sleep(0.02)
        result = run.get("result") or {}
        changes = {g: settings_diff(before[g], self.values(g)) for g in (VAL, CS)}
        plan = result.get("plan") or {}
        recorded = {
            "message": message,
            "game": game,
            "status": run["status"],
            "source": (result.get("provenance") or {}).get("source"),
            "fallbackReason": (result.get("provenance") or {}).get("fallbackReason"),
            "latencyMs": run.get("latencyMs"),
            "modelCalls": (run.get("validation") or {}).get("modelCalls") or [],
            "toolCalls": len(run.get("toolCalls") or []),
            "intent": result.get("intent"),
            "scope": plan.get("scope"),
            "goalDimensions": result.get("goalDimensions"),
            "reply": result.get("reply"),
            "explanations": result.get("explanations") or [],
            "navigation": result.get("navigateTo"),
            "recommendations": [{k: rec.get(k) for k in ("settingId", "currentValue", "proposedValue",
                                                           "whyForGoal", "tradeoff", "dimension", "basedOn")}
                                for rec in result.get("recommendations", [])],
            "memory": [{k: update.get(k) for k in ("kind", "dimension", "scope", "game", "factKey", "valueText")}
                       for update in result.get("appliedMemoryUpdates", [])],
            "comparisonIds": [c["id"] for c in result.get("crossGameComparisons", [])],
            "stagedCount": result.get("stagedCount", 0),
            "coverage": plan.get("coverage"),
            "filtered": result.get("filtered", []),
            "unauthorizedChanges": {g: d for g, d in changes.items() if d},
        }
        self.turns.append(recorded)
        return result

    def proposal(self, result):
        pid = result.get("stagedProposalId")
        return self.request("GET", f"/proposals/{pid}") if pid else None

    def apply(self, proposal, items=None, *, key=None):
        if proposal is None:
            return None
        choices = proposal["items"] if items is None else items
        if not choices:
            return None
        return self.request("POST", f"/proposals/{proposal['id']}/apply",
                            {"itemIds": [item["id"] for item in choices], "idempotencyKey": key})

    def check(self, code, passed, detail=None):
        self.results["checks"].append({"case": self.group, "check": code, "passed": bool(passed),
                                       "repetition": self.repetition, "detail": detail})

    def finish(self):
        self.results["turns"].extend([{"case": self.group, "repetition": self.repetition, **t} for t in self.turns])


def pilot(s, name):
    spec = PILOTS[name]
    game, criteria = spec["game"], spec["criteria"]
    s.select(game, "baseline")
    s.manual(game, {sid: rubric[0] for sid, rubric in criteria.items()})
    if name == "b2":
        s.manual(game, {"cs2.video.boost_player_contrast": "1", "cs2.video.dynamic_shadows": "1"})
    s.select(game)
    before = s.values(game)
    result = s.turn(game, spec["prompt"])
    recs = {rec["settingId"]: rec["proposedValue"] for rec in result.get("recommendations", [])}
    proposal = s.proposal(result)
    applied = s.apply(proposal, key=f"audit-{name}")
    after = s.values(game)
    changed = settings_diff(before, after)
    protected = {sid for sid in before if sid.startswith(("val.controls.", "val.audio.", "val.crosshair.",
                                                          "cs2.kbmouse.", "cs2.audio.", "cs2.crosshair."))
                 or sid.endswith((".resolution", ".aspect_ratio", ".aspect_ratio_method"))}
    protected_recs = sorted(protected & recs.keys())
    protected_changes = sorted(protected & changed.keys())
    s.check("protect_requested_categories", not protected_recs and not protected_changes,
            {"recommendations": protected_recs, "committed": protected_changes})

    def scores(values):
        return {sid: 1 if values.get(sid) in rubric[1] else 0.5 if values.get(sid) in rubric[2] else 0
                for sid, rubric in criteria.items()}

    start_scores, end_scores = scores(before), scores(after)
    relevant = {sid: v for sid, v in recs.items() if sid in criteria}
    needed = {sid for sid, score in start_scores.items() if score != 1}
    good = {sid: v for sid, v in relevant.items() if sid in needed and scores({sid: v})[sid] > start_scores[sid]}
    unrelated_or_optional = sorted(recs.keys() - criteria.keys())
    changed_aligned = sorted(set(changed) & (criteria.keys() - needed))
    staged = {item["settingId"]: item["effectiveValue"] for item in (proposal or {}).get("items", [])}
    s.check("all_pilot_criteria_full_credit", sum(end_scores.values()) == 8,
            {"startingScore": sum(start_scores.values()), "finalScore": sum(end_scores.values()),
             "criteria": {sid: {"from": before[sid], "to": after[sid], "points": end_scores[sid]} for sid in criteria},
             "scoredRecommendationCount": len(good), "totalRecommendationCount": len(recs),
             "coverageNumerator": len(good), "coverageDenominator": len(needed),
             "outsideRubricRecommendations": unrelated_or_optional, "changedAlreadyAligned": changed_aligned,
             "applyPolicy": "Apply all auto-staged items once, or record unchanged fixture when no proposal."})
    retained = {item["settingId"] for item in (result.get("plan") or {}).get("alreadyAlignedItems", [])}
    s.check("recognize_already_aligned", (criteria.keys() - needed) <= retained,
            {"expected": sorted(criteria.keys() - needed), "reported": sorted(retained)})
    s.check("apply_matches_review", bool(staged) and all(after.get(k) == v for k, v in staged.items()),
            {"staged": staged, "changed": changed, "source": (applied or {}).get("batch", {}).get("source")})
    if name == "b2":
        s.check("retain_visibility_aids", all(after[k] == "1" for k in
                                             ("cs2.video.boost_player_contrast", "cs2.video.dynamic_shadows")))


def onboarding(s):
    s.select(VAL, "baseline")
    before_cs = s.values(CS)
    edits = {
        "val.general.sensitivity_aim": 0.4,
        "val.controls.key_team_ptt": "B",
        "val.controls.key_ping": "X",
        "val.crosshair.primary_color": "cyan",
        "val.video.texture_quality": "med",
        "val.audio.overall_volume": 65,
    }
    batch = s.manual(VAL, edits)
    s.check("actual_manual_origin", len(batch.get("events", [])) == len(edits),
            {"edited": sorted(edits), "source": batch.get("source")})
    s.select(CS)
    cards = active_cards(s.discover(CS))
    evidence = {
        "cs2.kbmouse.mouse_sensitivity": "0.4",
        "cs2.kbmouse.key_mic": "B",
        "cs2.kbmouse.key_player_ping": "X",
    }
    relevant = {c["settingId"] for c in cards if c["settingId"] in evidence and c.get("crossGame")
                and c["kind"] == "inspect" and evidence[c["settingId"]] in c["why"]}
    s.check("proactive_use_of_manual_history", relevant == evidence.keys(),
            {"relevanceNumerator": len(relevant), "cardCount": len(cards), "coverageDenominator": len(evidence),
             "cards": card_items(cards)})
    s.check("no_inferred_durable_memory_from_manual_edits", not preference_items(s.profile(CS))
            and not s.profile(CS)["personalFacts"])
    response = s.turn(CS, "What CS2 sensitivity matches my VALORANT sensitivity?")
    comp = next((c for c in response.get("crossGameComparisons", []) if c["id"] == "mouse_sensitivity"), {})
    conversion = comp.get("sensitivityConversion") or {}
    value = conversion.get("convertedValue")
    s.check("chat_uses_same_evidence_and_direction", comp.get("sourceGame") == VAL
            and comp.get("targetGame") == CS and isinstance(value, (int, float)) and abs(value - 1.273) < 0.015
            and "dpi" in " ".join(conversion.get("assumptions") or []).lower(), conversion)
    ptt = next((c for c in cards if c["settingId"] == "cs2.kbmouse.key_mic"), None)
    checked = [] if not ptt else s.request("POST", "/games/cs2/relevant-now/check", {"checkId": ptt["checkId"]})["items"]
    s.check("review_and_mark_without_copying", any(c["settingId"] == "cs2.kbmouse.key_mic"
                                                   and c["state"] == "checked" for c in checked)
            and s.values(CS) == before_cs)


def reverse_analogues(s):
    s.select(CS, "baseline")
    s.manual(CS, {"cs2.kbmouse.mouse_sensitivity": 1.27, "cs2.kbmouse.key_mic": "B"})
    s.select(VAL)
    comparison = s.compare(VAL, "Convert my CS2 sensitivity to VALORANT")
    sens = next((c for c in comparison if c["id"] == "mouse_sensitivity"), {})
    conv = sens.get("sensitivityConversion") or {}
    s.check("reverse_conversion_from_actual_history",
            sens.get("sourceGame") == CS and sens.get("targetGame") == VAL
            and abs(float(conv.get("convertedValue") or 0) - 0.4) < 0.01, conv)
    voice = s.compare(VAL, "What is the VALORANT equivalent of the CS2 push-to-talk key?")
    s.check("voice_analogue_describes_team_party_difference",
            any("party" in c.get("differences", "").lower() and "team" in c.get("differences", "").lower()
                for c in voice), [{"id": c["id"], "differences": c.get("differences")} for c in voice])
    utility = s.compare(VAL, "Transfer my VALORANT ability keys to CS2 grenades")
    s.check("utility_transfer_has_an_explicit_limitation",
            any(any(word in (c.get("differences", "") + " " + (c.get("safetyNote") or "")).lower()
                    for word in ("one-to-one", "no direct", "differ", "analogy", "arbitrary", "blindly copy"))
                for c in utility), [{"id": c["id"], "safetyNote": c.get("safetyNote")} for c in utility])


def goals_journey(s):
    s.select(VAL)
    persistent = s.turn(VAL, "Remember that I usually prioritize high FPS.")
    s.check("explicit_durable_performance", any(p["scope"] == "durable" and p["dimension"] == "performance"
                                               for p in preference_items(s.profile(VAL))),
            preference_items(s.profile(VAL)))
    s.check("durable_declaration_does_not_set_immediate_goal",
            goals(s.profile(VAL), VAL) == [] and not persistent.get("stagedProposalId"),
            {"goals": goals(s.profile(VAL), VAL), "stagedCount": persistent.get("stagedCount", 0)})
    initial = s.turn(VAL, "Help me get smoother FPS and lower input lag.")
    s.check("immediate_performance_request_stages", bool(initial.get("stagedProposalId")),
            initial.get("goalDimensions"))
    mixed = s.turn(VAL, "I normally prioritize FPS, but tonight I want the game to look nice.")
    profile = s.profile(VAL)
    s.check("mixed_turn_has_only_current_visual_goal", goals(profile, VAL) == [["visual_quality"]],
            {"goals": goals(profile, VAL), "resultDimensions": mixed.get("goalDimensions"),
             "conflicts": profile["conflicts"][VAL]})
    s.check("temporary_goal_preserves_durable_memory", {p["dimension"] for p in profile["preferences"]
                                                       if p["scope"] == "durable"} == {"performance"},
            preference_items(profile))
    old = s.proposal(initial)
    discover = active_cards(s.discover(VAL))
    s.check("old_recommendation_becomes_stale_for_new_goal", bool(old and old["freshnessStatus"] == "outdated_goal"),
            None if old is None else old["freshnessStatus"])
    s.check("discover_tracks_current_objective",
            any(c.get("dimension") == "visual_quality" for c in discover), card_items(discover))
    s.turn(VAL, "Actually, I want better visual quality for tonight. Keep VSync unchanged.")
    s.request("DELETE", f"/games/{VAL}/session-goals")
    restored = s.profile(VAL)
    s.check("ending_temporary_goal_retains_previous_priority", not goals(restored, VAL)
            and any(p["scope"] == "durable" and p["dimension"] == "performance" for p in restored["preferences"]),
            {"goals": goals(restored, VAL), "preferences": preference_items(restored)})


def memory_scope(s):
    s.select(VAL)
    for game, message in (
        (VAL, "Remember that I prioritize input latency only in VALORANT."),
        (CS, "Remember that I deprioritize input latency in CS2."),
    ):
        s.select(game)
        s.turn(game, message)
    prefs = preference_items(s.profile(VAL))
    s.check("opposing_scoped_preferences_coexist",
            {(p["game"], p["direction"]) for p in prefs if p["dimension"] == "input_latency"}
            == {(VAL, "prioritize"), (CS, "deprioritize")}, prefs)
    s.select(CS)
    s.turn(CS, "Actually, forget what I said about wanting low input latency in CS2.")
    after = preference_items(s.profile(CS))
    s.check("chat_removal_preserves_other_game", {(p["game"], p["direction"]) for p in after
                                                if p["dimension"] == "input_latency"} == {(VAL, "prioritize")}, after)


def mixed_requests(s):
    s.select(CS)
    result = s.turn(CS, "Make CS2 run smoother, but don't change the resolution. Also explain what ambient "
                    "occlusion does, and remember that I usually prioritize visibility over graphics.")
    ids = [item["settingId"] for item in result.get("recommendations", [])]
    s.check("mixed_turn_has_performance_proposal",
            bool(result.get("stagedProposalId")) and "performance" in (result.get("goalDimensions") or []), ids)
    s.check("mixed_turn_respects_resolution_exclusion", "cs2.video.resolution" not in ids, ids)
    s.check("mixed_turn_includes_requested_explanation",
            any(e["settingId"] == "cs2.video.ambient_occlusion" for e in result.get("explanations", [])),
            result.get("explanations"))
    prefs = preference_items(s.profile(CS))
    s.check("mixed_turn_recognizes_explicit_preference",
            any(p["dimension"] == "visibility" and p["scope"] == "durable" for p in prefs), prefs)


def exact_and_recovery(s, game):
    settings = EXACT[game]
    s.select(game, "baseline")
    s.manual(game, {sid: spec[0] for sid, spec in settings.items()})
    s.select(game)
    junction = s.request("GET", f"/games/{game}/catalog")
    by_id = {item["id"]: item for item in junction["settings"]}
    configured = {}
    for sid, (_, target, message) in settings.items():
        before = s.values(game)
        result = s.turn(game, message)
        proposal = s.proposal(result)
        items = (proposal or {}).get("items", [])
        nav = (result.get("navigateTo") or {}).get("settingId")
        recommended = {item["settingId"]: item["effectiveValue"] for item in items}
        reply = result.get("reply") or ""
        route = by_id[sid]["canonicalPath"]
        if by_id[sid]["aiProposable"]:
            passed = recommended == {sid: target}
        else:
            # A valid manual route still requires a human edit. The fixed task value remains the test oracle.
            route_mentioned = nav == sid or route.lower() in reply.lower()
            target_spoken = bool(re.search(r"\b60\s*(?:%|percent)|\b0?\.6\b", reply)) if target == 60 else str(target) in reply
            passed = not items and route_mentioned and target_spoken
        s.check(f"exact_{by_id[sid]['key']}", passed,
                {"navigation": nav, "canonicalPath": route, "proposal": recommended,
                 "assistance": "stage" if by_id[sid]["aiProposable"] else "manual", "expectedValue": target})
        if recommended == {sid: target}:
            s.apply(proposal, key=f"audit-exact-{by_id[sid]['key']}")
            configured[sid] = "applied_from_chat"
        else:
            if items:
                s.request("POST", f"/proposals/{proposal['id']}/reject", {"reason": "Unrelated diagnostic proposal"})
            s.manual(game, {sid: target})
            configured[sid] = "manual_fixture_step"
        diff = settings_diff(before, s.values(game))
        if diff != {sid: [before[sid], target]}:
            raise RuntimeError(f"Exact journey changed unrelated values: {diff}")
    current = s.values(game)
    volume = next(sid for sid in settings if sid.endswith("_volume"))
    desired = settings[volume][0]
    result = s.turn(game, "Restore the volume to what it was before those changes, but keep everything else.")
    proposal = s.proposal(result)
    patch = {item["settingId"]: item["effectiveValue"] for item in (proposal or {}).get("items", [])}
    nav = (result.get("navigateTo") or {}).get("settingId")
    reply = result.get("reply") or ""
    returned_volume = bool(re.search(r"\b80\s*(?:%|percent)|\b0?\.8(?:0)?\b|\b80\b", reply))
    guided_restore = not patch and nav == volume and returned_volume and not by_id[volume]["aiProposable"]
    s.check("correct_targeted_historical_recovery", patch == {volume: desired} or guided_restore,
            {"proposal": patch, "navigation": nav, "expected": desired, "configuredBy": configured})
    if patch == {volume: desired}:
        s.apply(proposal, key="audit-targeted-volume-restore")
    elif guided_restore:
        s.manual(game, {volume: desired})
    s.check("recovery_changes_only_volume", settings_diff(current, s.values(game)) ==
            {volume: [current[volume], desired]}, settings_diff(current, s.values(game)))


def explain_case(s, game, message, target, concepts):
    s.select(game)
    result = s.turn(game, message)
    explanations = result.get("explanations") or []
    text = " ".join([result.get("reply") or "", *(e["explanation"] for e in explanations)])
    matched = [bool(re.search(pattern, text, re.I)) for pattern in concepts]
    nav = (result.get("navigateTo") or {}).get("settingId")
    s.check("grounded_concept_proxy", all(matched) and (target is None or target == nav
            or any(e["settingId"] == target for e in explanations)),
            {"matched": sum(matched), "conceptCount": len(concepts), "expectedSetting": target, "navigation": nav})
    s.check("read_only_explanation",
            not result.get("stagedProposalId") and not result.get("recommendations") and not goals(s.profile(game), game),
            {"intent": result.get("intent"), "goals": goals(s.profile(game), game)})


def navigate(s, game, message, sid):
    s.select(game)
    catalogue = {item["id"]: item for item in s.request("GET", f"/games/{game}/catalog")["settings"]}
    result = s.turn(game, message)
    nav = result.get("navigateTo") or {}
    s.check("stable_canonical_navigation",
            nav.get("settingId") == sid and nav.get("path") == catalogue[sid]["canonicalPath"]
            and not result.get("stagedProposalId"), {"actual": nav, "canonicalPath": catalogue[sid]["canonicalPath"]})


def discover_journey(s):
    s.select(VAL)
    initial = active_cards(s.discover(VAL))
    s.check("untouched_defaults_do_not_claim_personalization",
            all(not c["crossGame"] and c["kind"] == "inspect"
                and not re.search(r"you (prefer|confirmed|changed)", c["why"], re.I) for c in initial),
            card_items(initial))
    after_repeat = active_cards(s.discover(VAL))
    s.check("passive_discover_reads_stable", [c["cardId"] for c in initial] == [c["cardId"] for c in after_repeat])
    s.manual(VAL, {"val.audio.overall_volume": 79})
    after_edit = active_cards(s.discover(VAL))
    initial_ids, edit_ids = [c["cardId"] for c in initial], [c["cardId"] for c in after_edit]
    s.check("unrelated_manual_edit_does_not_churn_cards", initial_ids == edit_ids,
            {"unchangedCardIdCount": len(set(initial_ids) & set(edit_ids)),
             "before": [c["settingId"] for c in initial], "after": [c["settingId"] for c in after_edit]})
    relevant = active_cards(s.event(VAL, "frame_drops"))
    context = [c for c in relevant if c["triggerGroup"] == "context_event" and c["dimension"] == "performance"]
    s.check("responds_to_simulated_objective_without_duplicates",
            bool(context) and len({c["settingId"] for c in relevant}) == len(relevant), card_items(relevant))
    if context:
        sid, target = context[0]["settingId"], context[0]["targetValue"]
        dismissed = active_cards(s.request("POST", f"/games/{VAL}/relevant-now/dismiss", {"settingId": sid}))
        s.check("same_context_dismissal_persists", all(c["settingId"] != sid for c in dismissed))
        s.event(VAL, "ranked_session")
        returned = active_cards(s.event(VAL, "frame_drops"))
        s.check("returning_context_does_not_resurface_identical_dismissed_offer",
                not any(c["settingId"] == sid and c["targetValue"] == target for c in returned), card_items(returned))
        s.turn(VAL, "Actually tonight I want better visual quality and richer lighting.")
        mixed = active_cards(s.discover(VAL))
        s.check("new_objective_does_not_resurface_identical_dismissed_offer",
                not any(c["settingId"] == sid and c["targetValue"] == target for c in mixed), card_items(mixed))
    else:
        for check in ("same_context_dismissal_persists", "returning_context_does_not_resurface_identical_dismissed_offer",
                      "new_objective_does_not_resurface_identical_dismissed_offer"):
            s.check(check, False, "No performance-context card to dismiss")


def already_aligned(s):
    s.select(CS)
    start = s.values(CS)
    before = active_cards(s.discover(CS))
    blank = active_cards(s.event(CS, None))
    s.check("no_signal_no_proactive_change", not any(c["kind"] == "change" for c in before + blank),
            card_items(before + blank))
    ambiguous = s.turn(CS, "Just looking around for now.")
    s.check("ambiguous_context_abstains", not ambiguous.get("recommendations")
            and not ambiguous.get("stagedProposalId") and not goals(s.profile(CS), CS))
    result = s.turn(CS, "I want the highest practical FPS and clear enemies. Only change graphics settings.")
    recs = result.get("recommendations", [])
    s.check("already_aligned_avoids_unnecessary_changes",
            not recs and bool((result.get("plan") or {}).get("alreadyAlignedItems")),
            {"recommendations": [x["settingId"] for x in recs], "coverage": (result.get("plan") or {}).get("coverage")})
    s.check("already_aligned_values_remain", s.values(CS) == start)


def control_journey(s):
    s.select(CS)
    result = s.turn(CS, "Improve CS2's frame rate and visibility. Lower graphics quality where helpful.")
    proposal = s.proposal(result)
    if not proposal or len(proposal["items"]) < 2:
        for check in ("edit_and_reject_before_explicit_apply", "applied_history_records_choice", "undo_and_restage_are_safe",
                      "locked_item_cannot_apply"):
            s.check(check, False, "Need at least two recommendations for review flow")
        return
    editable = next((i for i in proposal["items"] if i["settingId"] == "cs2.video.msaa"),
                    proposal["items"][0])
    rejected = next(i for i in proposal["items"] if i["id"] != editable["id"])
    options = [x["value"] for x in editable["validOptions"] if x["value"] not in
               {editable["effectiveValue"], editable["baselineValue"]}]
    edited = options[0] if options else editable["effectiveValue"]
    state = s.values(CS)
    s.request("PATCH", f"/proposals/{proposal['id']}/items/{editable['id']}", {"value": edited})
    s.request("POST", f"/proposals/{proposal['id']}/reject", {"itemIds": [rejected["id"]]})
    before_apply = s.values(CS)
    applied = s.apply(proposal, [editable], key="audit-explicit-review")
    batch = applied["batch"]
    changed = settings_diff(state, s.values(CS))
    # CS2 derives a displayed preset label from the member values.
    setting_changes = {sid: diff for sid, diff in changed.items() if sid != "cs2.video.video_preset"}
    s.check("edit_and_reject_before_explicit_apply", before_apply == state
            and setting_changes == {editable["settingId"]: [editable["baselineValue"], edited]}
            and any(i["id"] == rejected["id"] and i["status"] == "rejected" for i in applied["proposal"]["items"]),
            changed)
    history = s.request("GET", f"/games/{CS}/history")
    s.check("applied_history_records_choice",
            any(row["batchId"] == batch["batchId"] and row.get("source") in ("fallback_applied", "ai_applied", "rule_applied")
                for row in history))
    s.request("POST", f"/history/{batch['batchId']}/undo", {})
    restage = s.request("POST", f"/history/{batch['batchId']}/restage")
    restaged = restage.get("proposal") or {}
    s.check("undo_and_restage_are_safe", s.values(CS) == state
            and any(i["settingId"] == editable["settingId"] and i["effectiveValue"] == edited
                    for i in restaged.get("items", [])),
            {"restagedSettings": [i["settingId"] for i in restaged.get("items", [])]})
    if restaged.get("items"):
        locked = restaged["items"][0]
        s.request("PUT", f"/games/{CS}/locks/{locked['settingId']}", {"on": True})
        s.request("POST", f"/proposals/{restaged['id']}/apply", {"itemIds": [locked["id"]]}, expected=(409, 422))
        s.check("locked_item_cannot_apply", s.values(CS) == state and locked["settingId"] in s.state(CS)["locks"])
    else:
        s.check("locked_item_cannot_apply", False, "No restaged item to lock")


def no_durable(s, message):
    s.select(VAL)
    result = s.turn(VAL, message)
    profile = s.profile(VAL)
    s.check("no_unconfirmed_durable_memory", not profile["preferences"] and not profile["personalFacts"],
            {"intent": result.get("intent"), "goals": goals(profile, VAL), "preferences": preference_items(profile)})


def unavailable_model(s):
    s.request("PUT", "/session", {"selectedGame": VAL, "condition": "adaptive", "aiMode": "local"})
    result = s.turn(VAL, "My game has FPS drops. Help it run smoother.")
    source = (result.get("provenance") or {}).get("source")
    s.check("unreachable_local_model_has_labelled_fallback", source == "fallback"
            and bool((result.get("provenance") or {}).get("fallbackReason")), source)


def protect_actionable_setting(s, game, message, protected):
    s.select(game)
    before = s.values(game)
    result = s.turn(game, message)
    proposal = s.proposal(result)
    recs = {rec["settingId"] for rec in result.get("recommendations", [])}
    s.apply(proposal)
    changed = settings_diff(before, s.values(game))
    s.check("narrow_exclusion_keeps_setting_unchanged_while_helping",
            bool(recs) and protected not in recs and protected not in changed,
            {"protected": protected, "recommendations": sorted(recs), "changed": changed})


def exact_batch(s):
    s.select(CS, "baseline")
    s.manual(CS, {"cs2.game.radar_rotating": "0", "cs2.game.telemetry_ping": "0"})
    s.select(CS)
    result = s.turn(CS, "Enable rotating radar, set Show ping to Always, and set Master Volume to 40%.")
    proposal = s.proposal(result)
    items = {i["settingId"]: i["effectiveValue"] for i in (proposal or {}).get("items", [])}
    s.check("combined_exact_request_preserves_all_other_controls",
            items == {"cs2.game.radar_rotating": "1", "cs2.game.telemetry_ping": "2", "cs2.audio.master_volume": 0.4},
            items)


CASES = {
    "a1_b1_onboarding": (onboarding, (), "project"),
    "b_objective_shift": (goals_journey, (), "project"),
    "a2": (pilot, ("a2",), "project"),
    "b2": (pilot, ("b2",), "project"),
    "a3_a4_exact_recovery": (exact_and_recovery, (VAL,), "project"),
    "b3_b4_exact_recovery": (exact_and_recovery, (CS,), "project"),
    "c_review_recovery": (control_journey, (), "project"),
    "e_already_aligned": (already_aligned, (), "project"),
    "mixed_request": (mixed_requests, (), "development"),
    "exclude_vsync": (protect_actionable_setting,
                      (VAL, "Optimize for a smoother frame rate, but don't change VSync.", "val.video.vsync"), "holdout"),
    "exclude_shadows": (protect_actionable_setting,
                        (CS, "Boost FPS and keep Global Shadow Quality as it is.", "cs2.video.global_shadow_quality"),
                        "holdout"),
    "combined_exact_request": (exact_batch, (), "holdout"),
    "memory_scope_correction": (memory_scope, (), "holdout"),
    "reverse_analogues": (reverse_analogues, (), "holdout"),
    "discover_events": (discover_journey, (), "development"),
    "navigate_minimap": (navigate, (VAL, "Where can I find the minimap zoom setting?", "val.general.minimap_zoom"), "holdout"),
    "navigate_cs2_audio": (navigate, (CS, "Take me to Master Volume.", "cs2.audio.master_volume"), "holdout"),
    "ambiguous_preference": (no_durable, ("I prefer readability over maximum FPS, just for today.",), "development"),
    "speculative_preference": (no_durable, ("Maybe later I might try prioritizing graphics quality.",), "holdout"),
    "hypothetical_frame_quality": (no_durable, ("What if I wanted more FPS next month?",), "holdout"),
    "model_unavailable": (unavailable_model, (), "development"),
}
for name, *args in EXPLANATIONS:
    CASES[f"explain_{name}"] = (explain_case, tuple(args), "project")


def summarize(results):
    groups = {}
    for case in results["cases"]:
        checks = [c for c in results["checks"] if c["case"] == case["id"]]
        turns = [t for t in results["turns"] if t["case"] == case["id"]]
        groups[case["id"]] = {
            "passed": sum(c["passed"] for c in checks),
            "checks": len(checks),
            "turns": len(turns),
            "provenance": {source: sum((t["source"] or "unknown") == source for t in turns)
                           for source in sorted({t["source"] or "unknown" for t in turns})},
        }
    calls = [call for turn in results["turns"] for call in turn["modelCalls"]]

    def token_summary(key):
        tracked = [c[key] for c in calls if isinstance(c.get(key), int)]
        return {"total": sum(tracked), "reportedBy": len(tracked), "callsRecorded": len(calls)}

    latencies = [t["latencyMs"] for t in results["turns"] if t.get("latencyMs") is not None]
    model_latencies = [t["latencyMs"] for t in results["turns"] if t["source"] == "ai"
                       and t.get("latencyMs") is not None]
    return {
        "groups": groups,
        "chatTurns": len(results["turns"]),
        "turnsWithUnauthorizedWrites": sum(bool(t["unauthorizedChanges"]) for t in results["turns"]),
        "assistantModelCalls": len(calls),
        "inputTokens": token_summary("inputTokens"),
        "outputTokens": token_summary("outputTokens"),
        "assistantToolCalls": sum(t["toolCalls"] for t in results["turns"]),
        "medianTurnMs": median(latencies) if latencies else None,
        "localMedianTurnMs": median(model_latencies) if model_latencies else None,
        "localMaxTurnMs": max(model_latencies) if model_latencies else None,
        "errors": len(results["errors"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1], help="checkout to test")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("fallback", "local"), default="fallback")
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES), help="run selected cases")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    repo = args.repo.resolve()
    if not (repo / "backend" / "app" / "main.py").is_file():
        parser.error("--repo must point to a GamePlan checkout")
    sys.path.insert(0, str(repo / "backend"))

    from app.config import get_settings
    from app.domain.scenarios import reset
    from app.services import build_services

    # create_app() loads cached settings at import time. Read benchmark process
    # variables while excluding the checkout's private application configuration.
    with patch("app.config._load_dotenv"):
        base = get_settings()
        from app.main import create_app

    selected = args.cases or list(CASES)
    if args.mode == "local" and not base.ollama_model:
        parser.error("--mode local needs a configured OLLAMA_MODEL")
    results = {
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "mode": args.mode,
        "model": base.ollama_model if args.mode == "local" else None,
        "localSettings": ({"temperature": base.ollama_temperature, "numCtx": base.ollama_num_ctx,
                           "think": base.ollama_think, "maxToolRounds": base.agent_max_tool_rounds,
                           "deadlineS": base.agent_deadline_s} if args.mode == "local" else None),
        "repetitions": args.repeat,
        "cases": [{"id": case, "split": CASES[case][2]} for case in selected],
        "checks": [],
        "turns": [],
        "errors": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for repetition in range(1, args.repeat + 1):
        for case in selected:
            run_case, extra, _split = CASES[case]
            with TemporaryDirectory(prefix="gameplan-audit-") as temp:
                tmp = Path(temp)
                settings = replace(base, db_path=tmp / "case.db", backup_dir=tmp / "backups", store_chat_history=True)
                if case == "model_unavailable":
                    settings = replace(settings, ollama_model="audit-missing-model:synthetic",
                                       ollama_base_url="http://127.0.0.1:9")
                services = build_services(settings)
                if case == "e_already_aligned":
                    reset(services.store, settings.scenario_dir, settings.backup_dir,
                          "well_configured_competitive", backup=False)
                with TestClient(create_app(services)) as client:
                    scenario = Scenario(client, args.mode, case, results, repetition)
                    try:
                        run_case(scenario, *extra)
                    except Exception as exc:
                        results["errors"].append({"case": case, "repetition": repetition, "type": type(exc).__name__,
                                                  "message": str(exc).replace(str(tmp), "<scratch directory>")})
                    finally:
                        scenario.finish()
            count = sum(c["case"] == case and c["repetition"] == repetition for c in results["checks"])
            print(f"{case} repeat {repetition}: {count} checks, {len(scenario.turns)} turns", flush=True)
            results["summary"] = summarize(results)
            checkpoint = args.out.with_suffix(args.out.suffix + ".tmp")
            checkpoint.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            checkpoint.replace(args.out)
    print(f"Recorded {len(results['cases'])} scenario groups, {len(results['checks'])} checks, "
          f"{len(results['turns'])} chat turns, and {len(results['errors'])} harness errors")
    return 1 if results["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
