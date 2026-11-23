"""Comprehensive acceptance tests for the Final Autonomy, Adaptivity & HCI Coherence Pass (Scenarios A-H)."""
from __future__ import annotations

import asyncio
import time

from app.agent.fallback import fallback_draft
from app.agent.intent import detect_explicit_memory, extract_sensitivity_number, is_goal_statement, is_speculative
from app.agent.schemas import AssistantDraft, DraftMemoryAction
from app.agent.scope import ScopePlan
from app.agent.validate import validate_draft
from app.domain.cross_game import compare_cross_game, parse_cross_game_direction
from app.domain.db import write_tx
from app.domain.observations import build_observed_summary, detect_fact_discrepancies, observe_setting
from app.domain.planner import build_coverage_audit
from app.domain.scenarios import reset


def _reset(services, client, scenario: str = "default", condition: str = "adaptive", game: str = "valorant"):
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, scenario, "full", backup=False)
    client.put("/api/session", json={"condition": condition, "selectedGame": game, "aiMode": "fallback"})


async def _run_turn(services, game: str, message: str):
    started = await services.runner.start(game, message, {"path": "Video > Graphics Quality"})
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status = services.runner.status(started["runId"])
        if status["status"] != "running":
            return status
        await asyncio.sleep(0.02)
    raise AssertionError("run did not finish in time")


def test_scenario_a_zero_config_observation_and_honest_onboarding(services, client):
    _reset(services, client, "default", "adaptive", "valorant")

    # Zero-config profile includes observed defaults without claiming personal intent
    prof = client.get("/api/profile?game=valorant").json()
    obs = prof["observed"]
    assert obs["keySettings"]
    assert all(not k["deliberate"] for k in obs["keySettings"])
    assert any(k["sourceKind"] == "default" for k in obs["keySettings"])
    assert obs["tentativeSignals"] == []

    # Manual edit is observed automatically as user_manual and generates tentative signal without saving durable pref
    client.put("/api/games/valorant/settings/val.video.bloom", json={"value": "off"})
    prof2 = client.get("/api/profile?game=valorant").json()
    assert prof2["preferences"] == []
    assert prof2["observed"]["recentActions"][0]["source"] == "manual"
    assert prof2["observed"]["tentativeSignals"], "Manual change should surface a tentative pattern without auto-saving"
    assert prof2["observed"]["tentativeSignals"][0]["tentative"] is True
    sig_dims = {s["dimension"] for s in prof2["observed"]["tentativeSignals"]}
    assert "performance" in sig_dims
    assert "visual_quality" not in sig_dims

    # Discover shows honest onboarding checks with whyOrigin and never claims "You prefer" on defaults
    rn = client.get("/api/games/valorant/relevant-now").json()
    assert 1 <= len(rn["items"]) <= 4
    for card in rn["items"]:
        assert card["whyOrigin"] == "onboarding_observation"
        assert "you prefer" not in card["why"].lower()
        assert "you confirmed" not in card["why"].lower()


def test_scenario_b_natural_goal_update_goal_shift_and_freshness(services, client):
    _reset(services, client, "default", "adaptive", "valorant")

    # Competitive FPS ask sets session goal and stages competitive proposal
    res1 = asyncio.run(_run_turn(services, "valorant", "I want smoother FPS and lower input lag"))["result"]
    assert res1["intent"] == "recommend" and res1["stagedProposalId"]
    prop_id = res1["stagedProposalId"]

    prop_initial = client.get(f"/api/proposals/{prop_id}").json()
    assert prop_initial["freshnessStatus"] == "consistent"

    # Goal shift to visual quality marks pending competitive proposal outdated_goal and updates Discover
    res2 = asyncio.run(_run_turn(services, "valorant", "Actually today I care more about visual quality"))["result"]
    assert "visual_quality" in res2["goalDimensions"]
    prof = client.get("/api/profile?game=valorant").json()
    assert prof["sessionGoals"]["valorant"][0]["dimensions"][0] == "visual_quality"

    prop_after = client.get(f"/api/proposals/{prop_id}").json()
    assert prop_after["freshnessStatus"] == "outdated_goal"
    assert prop_after["freshnessWarning"]

    # Discover proactively synced to visual quality without needing manual Refresh
    rn = client.get("/api/games/valorant/relevant-now").json()
    assert rn["trigger"] in ("goal_change", "memory_update")


def test_scenario_c_neutral_explain_and_speculative_do_not_commit_memory(services, client):
    _reset(services, client, "default", "adaptive", "valorant")

    # Pure explanation does not save a session goal or preferences
    exp = asyncio.run(_run_turn(services, "valorant", "What does V-Sync do?"))["result"]
    assert exp["intent"] == "explain"
    assert exp["recommendations"] == []
    assert exp.get("goalDimensions", []) == []

    # Speculative remark never commits a goal, preference, or fact
    assert is_speculative("I might try visual quality over FPS later")
    spec = asyncio.run(_run_turn(services, "valorant", "I might try visual quality over FPS later"))["result"]
    assert spec["intent"] == "clarify"
    assert spec["recommendations"] == []
    assert spec.get("appliedMemoryUpdates", []) == []
    assert spec.get("preferenceSuggestions", []) == []

    prof = client.get("/api/profile?game=valorant").json()
    assert prof["sessionGoals"]["valorant"] == []
    assert prof["preferences"] == []
    assert prof["personalFacts"] == []


def test_scenario_d_explicit_memory_save_and_undo_vs_ambiguous_chip(services, client):
    _reset(services, client, "default", "adaptive", "valorant")

    # Ambiguous preference statement yields PreferenceChip rather than auto-saving
    ambig = fallback_draft(services.store, services.profile, "valorant", "I prefer readability over maximum FPS, just for today", {})
    assert ambig.intent == "preference"
    assert ambig.preference_suggestions and ambig.preference_suggestions[0].scope == "session"
    assert ambig.explicit_memory_actions == []

    # Explicit memory directive saves push-to-talk key & durable preference withUndo IDs
    mem_ptt = asyncio.run(_run_turn(services, "valorant", "Remember that I prefer V for push-to-talk in VALORANT"))["result"]
    updates = mem_ptt.get("appliedMemoryUpdates", [])
    assert len(updates) == 1
    assert updates[0]["kind"] == "fact" and updates[0]["factKey"] == "push_to_talk_key" and updates[0]["valueText"] == "V"

    mem_fps = asyncio.run(_run_turn(services, "valorant", "From now on always prioritize high FPS"))["result"]
    pref_updates = mem_fps.get("appliedMemoryUpdates", [])
    assert len(pref_updates) == 1 and pref_updates[0]["kind"] == "preference" and pref_updates[0]["scope"] == "durable"

    prof = client.get("/api/profile?game=cs2").json()
    assert any(f["factKey"] == "push_to_talk_key" and f["valueText"] == "V" for f in prof["personalFacts"])
    assert any(p["dimension"] == "performance" and p["scope"] == "durable" for p in prof["preferences"])

    # Undo reverses saved memory cleanly
    client.delete(f"/api/profile/personal-facts/{updates[0]['id']}")
    client.delete(f"/api/profile/preferences/{pref_updates[0]['id']}")
    prof_after = client.get("/api/profile?game=cs2").json()
    assert prof_after["personalFacts"] == []
    assert prof_after["preferences"] == []


def test_scenario_e_directional_cross_game_live_observed_and_discrepancy(services, client):
    _reset(services, client, "default", "adaptive", "valorant")
    assert extract_sensitivity_number("What CS2 sensitivity matches my 0.35 VALORANT sensitivity?") == 0.35

    # Manual sensitivity edit in VALORANT without any saved personal_setup_facts works automatically for VALORANT -> CS2
    client.put("/api/games/valorant/settings/val.general.sensitivity_aim", json={"value": 0.4})
    res = asyncio.run(_run_turn(services, "valorant", "What CS2 sensitivity matches my VALORANT sensitivity?"))["result"]
    comps = res.get("crossGameComparisons", [])
    assert comps
    sens_comp = next(c for c in comps if c["id"] == "mouse_sensitivity")
    assert sens_comp["sourceGame"] == "valorant"
    assert sens_comp["targetGame"] == "cs2"
    assert sens_comp["targetNavigateGame"] == "cs2"
    assert sens_comp["targetNavigateId"] == "cs2.kbmouse.mouse_sensitivity"
    assert sens_comp["sensitivityConversion"]["convertible"] is True
    assert round(sens_comp["sensitivityConversion"]["convertedValue"], 2) == 1.27

    # Discrepancy detection: save conflicting remembered fact 0.30 while live VALORANT is 0.40
    client.post(
        "/api/profile/personal-facts",
        json={"factKey": "mouse_sensitivity", "valueText": "0.30", "originGame": "valorant", "source": "user_explicit"},
    )
    res_disc = client.get("/api/cross-game/compare?game=valorant&q=convert%20my%20valorant%20sensitivity%20to%20cs2").json()
    disc_comp = next(c for c in res_disc["comparisons"] if c["id"] == "mouse_sensitivity")
    assert disc_comp.get("discrepancyNote")
    assert "0.30" in disc_comp["discrepancyNote"] and "0.4" in disc_comp["discrepancyNote"]

    # Explicit reverse direction CS2 -> VALORANT while in VALORANT
    src_g, tgt_g, exp_dir = parse_cross_game_direction("Convert my CS2 sensitivity to VALORANT", "valorant")
    assert (src_g, tgt_g, exp_dir) == ("cs2", "valorant", True)


def test_scenario_f_tradeoff_retention_and_historical_restage_freshness(services, client):
    _reset(services, client, "default", "adaptive", "valorant")

    # User strongly prioritizes visual quality (durable + session weight > chat performance ask)
    client.post(
        "/api/profile/preferences",
        json={"dimension": "visual_quality", "direction": "prioritize", "scope": "durable", "source": "user_explicit", "game": "valorant"},
    )
    client.post(
        "/api/profile/preferences",
        json={"dimension": "visual_quality", "direction": "prioritize", "scope": "session", "source": "user_explicit", "game": "valorant"},
    )
    # Apply a change when goal was competitive FPS first to record a batch
    res_comp = asyncio.run(_run_turn(services, "valorant", "I want higher frame rate"))["result"]
    assert res_comp["plan"].get("tradeoffRetainedItems"), "Opposing visual_quality priority should populate tradeoffRetainedItems"
    assert res_comp["plan"]["coverage"]["tradeoffRetainedCount"] >= 1

    # Stage & apply one FPS item, then shift goal to visual_quality, then restage that earlier FPS batch -> historical_preference warning
    prop_id = res_comp["stagedProposalId"]
    if prop_id:
        prop = client.get(f"/api/proposals/{prop_id}").json()
        first_item = prop["items"][0]["id"]
        apply_res = client.post(f"/api/proposals/{prop_id}/apply", json={"itemIds": [first_item]}).json()
        batch_id = apply_res["batch"]["batchId"]
        # Revert setting manually so restage has a diff to propose
        client.put(f"/api/games/valorant/settings/{prop['items'][0]['settingId']}", json={"value": prop["items"][0]["baselineValue"]})
        # Now shift current session goal to visual_quality
        asyncio.run(_run_turn(services, "valorant", "I want better visual quality today"))
        restage = client.post(f"/api/history/{batch_id}/restage").json()
        if restage.get("proposal"):
            restaged_prop = client.get(f"/api/proposals/{restage['proposal']['id']}").json()
            assert restaged_prop["freshnessStatus"] == "historical_preference"
            assert restaged_prop["freshnessWarning"]


def test_scenario_g_followup_resolution_checked_and_undo_lifecycle(services, client):
    _reset(services, client, "default", "adaptive", "valorant")

    # Manual VSync Off triggers Reflex follow-up automatically via route sync
    bat = client.put("/api/games/valorant/settings/val.video.vsync", json={"value": "off"}).json()
    rn = client.get("/api/games/valorant/relevant-now").json()
    fup = next((c for c in rn["items"] if c.get("ruleId") == "val_vsync_off_check_reflex"), None)
    assert fup is not None and fup["state"] == "suggested"

    # Undo trigger batch retires the follow-up cleanly as no_longer_relevant
    client.post(f"/api/history/{bat['batchId']}/undo", json={})
    rn_after_undo = client.get("/api/games/valorant/relevant-now").json()
    assert not any(c.get("ruleId") == "val_vsync_off_check_reflex" and c["state"] == "suggested" for c in rn_after_undo["items"])

    # Onboarding checked vs applied distinct state & cross-game completion persistence
    _reset(services, client, "valorant_onboarding_to_cs2", "adaptive", "cs2")
    rn_cs2 = client.get("/api/games/cs2/relevant-now").json()
    first_ob = rn_cs2["items"][0]
    checked = client.post("/api/games/cs2/relevant-now/check", json={"checkId": first_ob["checkId"]}).json()
    assert checked["items"][0]["state"] == "checked"


def test_scenario_h_preference_evidence_isolation_and_history_excerpt_flag(services, client):
    _reset(services, client, "default", "adaptive", "valorant")
    p1 = client.post(
        "/api/profile/preferences",
        json={"dimension": "performance", "direction": "prioritize", "scope": "durable", "source": "user_explicit", "game": "valorant", "note": "Need smooth 144Hz"},
    ).json()
    p2 = client.post(
        "/api/profile/preferences",
        json={"dimension": "visibility", "direction": "prioritize", "scope": "durable", "source": "user_explicit", "game": "valorant", "note": "Clear enemy silhouettes"},
    ).json()
    prof = client.get("/api/profile?game=valorant").json()
    pref_perf = next(p for p in prof["preferences"] if p["id"] == p1["id"])
    pref_vis = next(p for p in prof["preferences"] if p["id"] == p2["id"])
    assert all("smooth 144Hz" in (e["detail"] or "") for e in pref_perf["evidence"])
    assert all("smooth 144Hz" not in (e["detail"] or "") for e in pref_vis["evidence"])
    assert pref_perf["evidence"][0]["sourceCategory"] == "explicit_statement"

    # Long chat message (>120 chars) retains full verbatim userRequest in history (userRequestIsExcerpt == False)
    long_msg = "I am experiencing frame drops during heavy rounds in VALORANT and I want higher FPS cleanly right now; what settings should I change?"
    res = asyncio.run(_run_turn(services, "valorant", long_msg))["result"]
    prop = client.get(f"/api/proposals/{res['stagedProposalId']}").json()
    client.post(f"/api/proposals/{prop['id']}/apply", json={"itemIds": [prop["items"][0]["id"]]})
    hist = client.get("/api/games/valorant/history").json()
    assert hist[0]["provenance"]["userRequest"] == long_msg
    assert hist[0]["provenance"]["userRequestIsExcerpt"] is False


def test_validate_draft_backfills_goal_dimensions_for_local_llm(services, client):
    _reset(services, client, "default", "adaptive", "valorant")

    # Recommending without explicit draft.goal_dimensions backfills goalDimensions and marks goalChanged
    fps_scope = ScopePlan(
        scope="category_optimization",
        max_recs=12,
        auto_stage=True,
        include_minor=False,
        is_supplement=False,
        reason="test",
        inferred_dimensions=["performance", "input_latency"],
    )
    res1 = validate_draft(
        services.store,
        "valorant",
        AssistantDraft(intent="recommend", reply="Prepared FPS suggestions.", goal_dimensions=[]),
        source="ai",
        scope_plan=fps_scope,
        message="I want higher FPS and lower input lag",
    )
    assert res1["goalDimensions"] == ["performance", "input_latency"]
    assert res1["goalChanged"] is True

    # Goal shift phrasing backfills even if scope_plan had no inferred_dimensions
    empty_scope = ScopePlan(
        scope="explain_only",
        max_recs=0,
        auto_stage=False,
        include_minor=False,
        is_supplement=False,
        reason="test",
        inferred_dimensions=[],
    )
    res2 = validate_draft(
        services.store,
        "valorant",
        AssistantDraft(intent="recommend", reply="Focus on visual quality.", goal_dimensions=[]),
        source="ai",
        scope_plan=empty_scope,
        message="Actually today I care more about visual quality",
    )
    assert res2["goalDimensions"] == ["visual_quality"]
    assert res2["goalChanged"] is True

    # Explicit memory directive & speculative remarks never populate goalDimensions or goalChanged
    mem_res = validate_draft(
        services.store,
        "valorant",
        AssistantDraft(
            intent="preference",
            reply="Saved high FPS priority.",
            goal_dimensions=[],
            explicit_memory_actions=[
                DraftMemoryAction(
                    kind="preference",
                    dimension="performance",
                    scope="durable",
                    user_quote="From now on always prioritize high FPS",
                )
            ],
        ),
        source="ai",
        scope_plan=fps_scope,
        message="From now on always prioritize high FPS",
    )
    assert mem_res["goalDimensions"] == []
    assert mem_res["goalChanged"] is False

    spec_res = validate_draft(
        services.store,
        "valorant",
        AssistantDraft(intent="clarify", reply="Noted.", goal_dimensions=["visual_quality"]),
        source="ai",
        scope_plan=empty_scope,
        message="I might try visual quality sometime",
    )
    assert spec_res["goalDimensions"] == []
    assert spec_res["goalChanged"] is False
