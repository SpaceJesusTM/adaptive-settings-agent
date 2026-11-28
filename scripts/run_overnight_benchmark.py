"""Independent GamePlan continuation cases. Use identical --cases and --repeat for each --repo.

The original audit runner remains unmodified. The bench excludes checkout .env, uses
fresh SQLite per case, and writes synthetic traces only. With --mode local, set an
installed local OLLAMA_MODEL explicitly. Run local comparisons sequentially.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_audit_benchmark as audit

VAL, CS = audit.VAL, audit.CS
AO = "cs2.video.ambient_occlusion"
REFLEX = "cs2.video.nvidia_reflex"
VSYNC = "cs2.video.vsync"
CS_VOLUME = "cs2.audio.master_volume"
FIDELITY_CONTROLS = {"val.video.anti_aliasing", "val.video.texture_quality", "val.video.anisotropic_filtering"}
FPS_CONTROLS = {REFLEX, VSYNC, "cs2.video.msaa", "cs2.video.shader_detail", "cs2.video.particle_detail", AO}
VISIBILITY_CONTROLS = {"cs2.video.boost_player_contrast", "cs2.video.dynamic_shadows", "cs2.video.global_shadow_quality"}


class Scenario(audit.Scenario):
    def request(self, method, path, data=None, *, expected=None):
        payload = super().request(method, path, data, expected=expected)
        if method == "GET" and path.startswith("/chat/runs/") and payload["status"] != "running":
            self.finished_run = payload
        return payload

    def turn(self, game, message):
        self.finished_run = {}
        result = super().turn(game, message)
        row = self.turns[-1]
        row["validation"] = self.finished_run.get("validation") or {}
        row["toolTrace"] = self.finished_run.get("toolCalls") or []
        row["plan"] = result.get("plan")
        row["clarifyingQuestion"] = result.get("clarifyingQuestion")
        return result


def proposal_values(s, result):
    return {row["settingId"]: row["effectiveValue"] for row in (s.proposal(result) or {}).get("items", [])
            if row["status"] == "pending"}


def mentioned_settings(result):
    navigation = result.get("navigateTo") or {}
    return {navigation.get("settingId")} | {e.get("settingId") for e in result.get("explanations", [])}


def visible_text(result):
    return " ".join([result.get("reply") or "", *(e["explanation"] for e in result.get("explanations", []))])


def no_confirmed_memory(s, game):
    profile = s.profile(game)
    return not profile["preferences"] and not profile["personalFacts"]


def fixture_proposal(s, game, targets):
    return s.request("POST", "/proposals", {"game": game, "source": "rules", "title": "Synthetic draft fixture",
                                           "items": [{"settingId": sid, "proposedValue": value}
                                                     for sid, value in targets.items()]})


def attempt_apply(s, proposal):
    response = s.client.post(f"/api/proposals/{proposal['id']}/apply",
                             json={"itemIds": [item["id"] for item in proposal["items"]]})
    return {"status": response.status_code, "body": response.json()}


def mixed_envelope(s):
    s.select(CS)
    s.manual(CS, {VSYNC: "1", REFLEX: "0", AO: "3", "cs2.video.msaa": "8"})
    result = s.turn(CS, "Could you make the frame rate steadier without touching my resolution or anti-aliasing? "
                       "Also tell me what ambient occlusion does. Remember that I put seeing enemies ahead of graphics quality.")
    staged = proposal_values(s, result)
    s.check("mixed_change_component", bool(staged.keys() & (FPS_CONTROLS - {"cs2.video.msaa"})), staged)
    s.check("mixed_exclusions", not (staged.keys() & {"cs2.video.resolution", "cs2.video.msaa"}), staged)
    s.check("mixed_explanation_grounded", AO in mentioned_settings(result)
            and bool(re.search(r"contact|corner|crevic|shad", visible_text(result), re.I)),
            {"links": sorted(k for k in mentioned_settings(result) if k)})
    confirmed = {p["dimension"] for p in s.profile(CS)["preferences"] if p["scope"] == "durable" and p["direction"] == "prioritize"}
    s.check("mixed_memory_isolated", confirmed == {"visibility"}, sorted(confirmed))


def explain_ao(s):
    s.select(CS)
    result = s.turn(CS, "Are those little dark creases around corners from ambient occlusion or the same shadows that players cast? "
                       "Show me where to inspect ambient occlusion without changing anything.")
    text = visible_text(result)
    s.check("contrast_and_consequence", bool(re.search(r"contact|creases|corners|crevic", text, re.I))
            and bool(re.search(r"player|objects?|light source|cast shadow", text, re.I))
            and bool(re.search(r"depth|performance|frame rate|gpu", text, re.I)), text)
    s.check("ao_canonical_link", AO in mentioned_settings(result), sorted(k for k in mentioned_settings(result) if k))
    s.check("explanation_read_only", not result.get("recommendations") and not result.get("stagedProposalId")
            and not audit.goals(s.profile(CS), CS) and no_confirmed_memory(s, CS))


def tempo_visibility(s):
    s.select(CS)
    s.manual(CS, {"cs2.video.boost_player_contrast": "0", "cs2.video.dynamic_shadows": "0", "cs2.video.msaa": "4"})
    result = s.turn(CS, "I can give up a few frames if opponents remain easier to pick out. "
                       "Leave resolution, anti-aliasing, and the feel of aiming alone.")
    staged = proposal_values(s, result)
    s.check("comparative_goal_keeps_visibility_primary", bool(staged.keys() & VISIBILITY_CONTROLS)
            and "performance" not in (result.get("goalDimensions") or []), staged)
    protected = {"cs2.video.resolution", "cs2.video.msaa", "cs2.kbmouse.mouse_sensitivity", "cs2.kbmouse.zoom_sensitivity"}
    s.check("comparative_goal_respects_exclusions", not staged.keys() & protected, staged)


def exact_temporal(s, game, setting_id, initial, target, prompt, manual_display=None):
    s.select(game)
    s.manual(game, {setting_id: initial})
    result = s.turn(game, prompt)
    staged = proposal_values(s, result)
    if manual_display:
        passed = not staged and setting_id in mentioned_settings(result) and manual_display in visible_text(result)
    else:
        passed = staged == {setting_id: target}
        s.apply(s.proposal(result))
        passed = passed and s.values(game)[setting_id] == target
    s.check("temporal_request_exact_value_and_only_target", passed,
            {"expectedSetting": setting_id, "expectedValue": target, "staged": staged, "reply": visible_text(result)})
    s.check("temporary_edit_is_not_profile_memory", no_confirmed_memory(s, game) and not audit.goals(s.profile(game), game))


def implicit_history(s):
    s.select(CS)
    s.manual(CS, {CS_VOLUME: 0.81})
    s.manual(CS, {CS_VOLUME: 0.43, "cs2.game.telemetry_ping": "2"})
    result = s.turn(CS, "Could you put my master volume back where it was before I touched it? Keep the other edit.")
    staged = proposal_values(s, result)
    before = s.values(CS)
    s.apply(s.proposal(result))
    changed = audit.settings_diff(before, s.values(CS))
    s.check("implicit_history_restores_only_the_named_value", staged == {CS_VOLUME: 0.81}
            and changed == {CS_VOLUME: [0.43, 0.81]}, {"staged": staged, "changed": changed})


def voice_habit(s):
    s.select(CS)
    result = s.turn(CS, "For CS2, I always use push-to-talk. That's how I prefer voice chat.")
    facts = [f for f in s.profile(CS)["personalFacts"] if f["factKey"] == "voice_activation"]
    s.check("voice_modality_keeps_its_scope_and_meaning", len(facts) == 1
            and facts[0].get("originGame") == CS
            and bool(re.search(r"push.?to.?talk|push.?to.?use", facts[0]["valueText"], re.I))
            and not result.get("stagedProposalId"), facts)


def ambiguous_or_quoted(s, game, prompt, clarify):
    s.select(game)
    result = s.turn(game, prompt)
    s.check("ambiguity_or_quotation_creates_no_action_or_memory", no_confirmed_memory(s, game)
            and not result.get("recommendations") and not result.get("stagedProposalId")
            and not audit.goals(s.profile(game), game))
    if clarify:
        s.check("missing_reference_elicits_clarification", bool(result.get("clarifyingQuestion"))
                or result.get("intent") == "clarify", result.get("reply"))


def current_visual(s):
    s.select(VAL)
    s.manual(VAL, {"val.video.texture_quality": "low", "val.video.anti_aliasing": "none"})
    result = s.turn(VAL, "The game feels fine, but edges and surfaces look a little muddy. How could I sharpen the image "
                        "without changing my resolution or crosshair?")
    staged = proposal_values(s, result)
    s.check("implicit_visual_request_yields_relevant_options", bool(staged.keys() & FIDELITY_CONTROLS)
            and not any(sid.startswith("val.crosshair.") or sid.endswith(".resolution") for sid in staged), staged)


def pending_protection(s):
    s.select(CS)
    s.manual(CS, {VSYNC: "1", REFLEX: "0"})
    s.turn(CS, "Improve frame pacing and responsiveness.")
    # Discard the broad draft only. Stage an exact comparable target through the existing proposal API.
    for pending in s.request("GET", "/games/cs2/proposals?status=pending"):
        s.request("POST", f"/proposals/{pending['id']}/reject", {"reason": "Clear setup draft before the fixture."})
    draft = fixture_proposal(s, CS, {REFLEX: "1"})
    s.turn(CS, "Keep NVIDIA Reflex Low Latency unchanged.")
    before = s.values(CS)
    applied = attempt_apply(s, draft)
    after = s.values(CS)
    s.check("new_protection_blocks_previous_draft_apply", 400 <= applied["status"] < 500
            and before == after, {"responseStatus": applied["status"], "changed": audit.settings_diff(before, after)})
    s.manual(CS, {REFLEX: "2"})
    s.check("direct_manual_intent_still_allowed", s.values(CS)[REFLEX] == "2")


def stale_revision(s):
    s.select(CS)
    s.manual(CS, {"cs2.video.msaa": "8"})
    draft = fixture_proposal(s, CS, {"cs2.video.msaa": "2"})
    s.manual(CS, {"cs2.video.msaa": "4"})
    before = s.values(CS)
    applied = attempt_apply(s, draft)
    s.check("manual_revision_wins_over_old_draft", 400 <= applied["status"] < 500 and s.values(CS) == before,
            {"responseStatus": applied["status"], "value": s.values(CS)["cs2.video.msaa"]})


def longitudinal_visibility(s, control=False):
    s.select(CS, "baseline")
    # Same final values in both fixtures. Evidence variant distributes manually selected visibility aids over sessions.
    s.manual(CS, {"cs2.video.boost_player_contrast": "0", "cs2.video.dynamic_shadows": "0"})
    if control:
        s.apply(fixture_after_select(s, CS, {"cs2.video.boost_player_contrast": "1", "cs2.video.dynamic_shadows": "1"}))
        s.request("POST", "/admin/reset", {"mode": "ai_only"})
    else:
        s.manual(CS, {"cs2.video.boost_player_contrast": "1"})
        s.request("POST", "/admin/reset", {"mode": "ai_only"})
        s.select(CS, "baseline")
        s.manual(CS, {"cs2.video.dynamic_shadows": "1"})
        s.request("POST", "/admin/reset", {"mode": "ai_only"})
    s.select(CS)
    profile = s.profile(CS)
    signals = profile["observed"].get("tentativeSignals", [])
    observed = next((item for item in signals if item.get("dimension") == "visibility"), None)
    s.check("independent_manual_history_differs_from_accepting_a_draft", bool(observed) is not control
            and no_confirmed_memory(s, CS), {"signals": signals, "visibilityControls": {k: s.values(CS)[k] for k in VISIBILITY_CONTROLS}})


def fixture_after_select(s, game, values):
    s.select(game)
    return fixture_proposal(s, game, values)


def discover_avoid_pending(s):
    s.select(CS)
    s.manual(CS, {VSYNC: "1", REFLEX: "0", "cs2.video.msaa": "8", AO: "3"})
    draft = fixture_proposal(s, CS, {REFLEX: "1", VSYNC: "0"})
    cards = audit.active_cards(s.event(CS, "frame_drops"))
    pending = {item["settingId"] for item in draft["items"]}
    visible_edits = {c["settingId"] for c in cards if c["kind"] == "change"}
    s.check("discover_adds_distinct_eligible_information", bool(visible_edits) and not visible_edits & pending
            and len(visible_edits) == len([c for c in cards if c["kind"] == "change"]), audit.card_items(cards))


def discover_contact_shadows(s):
    s.select(CS)
    s.manual(CS, {"cs2.video.dynamic_shadows": "1", "cs2.video.boost_player_contrast": "1"})
    result = s.turn(CS, "I want visibility in dark areas, but don't change any video settings for me. "
                       "Help me find something unfamiliar worth understanding.")
    cards = audit.active_cards(s.discover(CS))
    # Independently chosen discovery families for this objective. Exact order within them is free.
    relevant = {"cs2.video.dynamic_shadows", "cs2.video.boost_player_contrast",
                "cs2.video.ambient_occlusion", "cs2.video.global_shadow_quality"}
    s.check("discovery_teaches_without_editing_protected_video", any(c["kind"] == "inspect" and c["settingId"] in relevant for c in cards)
            and not any(c["kind"] == "change" and c["settingId"].startswith("cs2.video.") for c in cards)
            and not result.get("stagedProposalId"), audit.card_items(cards))


def explain_pending(s):
    s.select(CS)
    s.manual(CS, {REFLEX: "0"})
    fixture_proposal(s, CS, {REFLEX: "1"})
    result = s.turn(CS, "Did I already enable NVIDIA Reflex Low Latency or is that just waiting in the review tray? "
                       "Please explain the difference before I do anything.")
    text = visible_text(result)
    status_supported = bool(re.search(r"pending|stage|review tray|not.*applied", text, re.I))
    false_action = bool(re.search(r"you (?:already|previously) (?:enabled|applied|changed)", text, re.I))
    s.check("pending_is_distinct_from_applied_state", status_supported and not false_action and s.values(CS)[REFLEX] == "0"
            and not result.get("stagedProposalId"), text)


CASES = {
    "live_a2": (audit.pilot, ("a2",), "frozen_pilot"),
    "live_b2": (audit.pilot, ("b2",), "frozen_pilot"),
    "frozen_mixed": (audit.mixed_requests, (), "frozen_pilot"),
    "frozen_explain_ao": next((audit.explain_case, tuple(args), "frozen_pilot")
                              for name, *args in audit.EXPLANATIONS if name == "ao"),
    "mixed_envelope": (mixed_envelope, (), "holdout"),
    "explain_ao": (explain_ao, (), "holdout"),
    "tempo_visibility": (tempo_visibility, (), "holdout"),
    "temporal_cs2_volume": (exact_temporal, (CS, CS_VOLUME, 0.8, 0.35, "This evening only, put Master Volume at 35 percent."), "holdout"),
    "temporal_val_volume": (exact_temporal, (VAL, "val.audio.overall_volume", 80, 45,
                           "For this session, set Overall Volume to 45%.", "45%"), "holdout"),
    "temporal_val_vsync": (exact_temporal, (VAL, "val.video.vsync", "on", "off",
                          "Switch VSync to Off just for tonight."), "holdout"),
    "implicit_history": (implicit_history, (), "holdout"),
    "voice_habit": (voice_habit, (), "holdout"),
    "ambiguous_reference": (ambiguous_or_quoted, (CS, "Put that back how I had it.", True), "holdout"),
    "quoted_hypothetical": (ambiguous_or_quoted, (VAL, "Someone wrote 'remember that I always want low input lag.' "
                            "What would that mean if a player really said it?", False), "holdout"),
    "current_visual": (current_visual, (), "holdout"),
    "pending_protection": (pending_protection, (), "safety"),
    "stale_revision": (stale_revision, (), "safety"),
    "longitudinal_visibility": (longitudinal_visibility, (), "behavior"),
    "accepted_plan_control": (longitudinal_visibility, (True,), "behavior_control"),
    "discover_avoid_pending": (discover_avoid_pending, (), "discovery"),
    "discover_contact_shadows": (discover_contact_shadows, (), "discovery"),
    "explain_pending": (explain_pending, (), "holdout"),
    "onboarding_from_real_edits": (audit.onboarding, (), "frozen_demo"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(audit.__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("fallback", "local"), default="fallback")
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--machine-label", help="Optional public hardware label, such as M4-24GB or RTX-4080-SUPER-16GB")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    repo = args.repo.resolve()
    if not (repo / "backend/app/main.py").is_file():
        parser.error("--repo must point to a GamePlan checkout")
    sys.path.insert(0, str(repo / "backend"))

    from app.config import get_settings
    from app.services import build_services

    with patch("app.config._load_dotenv"):
        settings = get_settings()
        from app.main import create_app

    if args.mode == "local" and not settings.ollama_model:
        parser.error("--mode local requires an explicit OLLAMA_MODEL")
    selected = args.cases or list(CASES)
    config_fields = (
        "ollama_temperature", "ollama_num_ctx", "ollama_think", "ollama_timeout_s",
        "agent_max_tool_rounds", "agent_deadline_s", "agent_fast_path",
        "agent_reasoning_mode", "agent_pipeline", "agent_discovery_policy",
    )
    results = {
        "benchmark": "overnight-v1",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "dirtyTrackedFiles": bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo, text=True)),
        "mode": args.mode,
        "model": settings.ollama_model if args.mode == "local" else None,
        "machine": {"label": args.machine_label, "system": platform.system(), "arch": platform.machine()},
        "configuration": {k: getattr(settings, k) for k in config_fields if hasattr(settings, k)},
        "repetitions": args.repeat,
        "cases": [{"id": name, "split": CASES[name][2]} for name in selected],
        "checks": [],
        "turns": [],
        "errors": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for repetition in range(1, args.repeat + 1):
        for case in selected:
            fixture, params, _ = CASES[case]
            with TemporaryDirectory(prefix="gameplan-overnight-") as directory:
                temp = Path(directory)
                isolated = replace(settings, db_path=temp / "case.db", backup_dir=temp / "backups", store_chat_history=True)
                with audit.TestClient(create_app(build_services(isolated))) as client:
                    s = Scenario(client, args.mode, case, results, repetition)
                    try:
                        fixture(s, *params)
                    except Exception as exc:
                        detail = str(exc).replace(directory, "<scratch directory>").replace(str(repo), "<checkout>")
                        results["errors"].append({"case": case, "repetition": repetition,
                                                  "type": type(exc).__name__, "message": detail})
                    finally:
                        s.finish()
            checks = [row for row in results["checks"] if row["case"] == case and row["repetition"] == repetition]
            print(f"{case} repeat {repetition}: {sum(row['passed'] for row in checks)}/{len(checks)} checks, "
                  f"{len(s.turns)} turns", flush=True)
            results["summary"] = audit.summarize(results)
            checkpoint = args.out.with_suffix(args.out.suffix + ".tmp")
            checkpoint.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            checkpoint.replace(args.out)
    return bool(results["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
