"""Backend acceptance tests for the Final HCI Design, Adaptivity & Research-Readiness Pass."""
from __future__ import annotations

import time

from app.domain.cross_game import convert_hipfire_sensitivity, validate_cross_game_mappings
from app.domain.scenarios import reset
from app.domain.store import Change

from .conftest import set_condition, value_of


def _poll_run(client, run_id: str) -> dict:
    for _ in range(250):
        st = client.get(f"/api/chat/runs/{run_id}").json()
        if st["status"] != "running":
            return st
        time.sleep(0.02)
    raise AssertionError("run timed out")


def test_history_provenance_truthfulness_superseded_and_safe_restaging(client, services):
    set_condition(services, "adaptive", aiMode="fallback")

    # Manual change must never fabricate AI rationale
    man = client.put("/api/games/valorant/settings/val.video.vignette", json={"value": "off"}).json()
    hist_manual = client.get("/api/games/valorant/history").json()
    assert hist_manual[0]["batchId"] == man["batchId"]
    assert hist_manual[0]["provenance"]["hasRecordedRationale"] is False
    assert hist_manual[0]["provenance"]["userRequest"] is None
    assert hist_manual[0]["events"][0]["why"] is None

    # AI / fallback chat proposal records real userRequest & per-item rationale when applied
    run = client.post(
        "/api/chat",
        json={"game": "valorant", "message": "Help reduce input latency by disabling VSync."},
    ).json()
    st = _poll_run(client, run["runId"])
    pid = st["result"]["stagedProposalId"]
    assert pid
    prop = client.get(f"/api/proposals/{pid}").json()
    vsync_item = next(i for i in prop["items"] if i["settingId"] == "val.video.vsync")
    applied = client.post(f"/api/proposals/{pid}/apply", json={"itemIds": [vsync_item["id"]]}).json()
    batch_id = applied["batch"]["batchId"]

    hist = client.get("/api/games/valorant/history").json()
    batch_entry = next(b for b in hist if b["batchId"] == batch_id)
    assert batch_entry["provenance"]["hasRecordedRationale"] is True
    assert "input latency" in (batch_entry["provenance"]["userRequest"] or "")
    assert batch_entry["events"][0]["why"]
    assert batch_entry["superseded"] is False

    # User manually turns VSync back On -> historical batch becomes superseded, and Restage offers editable proposal
    client.put("/api/games/valorant/settings/val.video.vsync", json={"value": "on"})
    hist2 = client.get("/api/games/valorant/history").json()
    sup_entry = next(b for b in hist2 if b["batchId"] == batch_id)
    assert sup_entry["superseded"] is True
    assert sup_entry["undoable"] is False

    # Restage creates a new editable proposal without changing any setting values yet
    restage = client.post(f"/api/history/{batch_id}/restage").json()
    assert restage["stagedCount"] == 1
    assert restage["proposal"]["source"] == "history"
    assert restage["proposal"]["restagedFromBatchId"] == batch_id
    assert value_of(services, "valorant", "val.video.vsync")["value"] == "on"

    # Restaging again after VSync is locked guards it instead of allowing blind apply
    client.put("/api/games/valorant/locks/val.video.vsync", json={"on": True})
    restage_locked = client.post(f"/api/history/{batch_id}/restage").json()
    assert restage_locked["stagedCount"] == 0
    assert restage_locked["lockedItems"][0]["settingId"] == "val.video.vsync"
    assert value_of(services, "valorant", "val.video.vsync")["value"] == "on"

    # Manual batch containing only a personal keybind -> restage surfaces manualConsiderations safely (no auto-stage)
    client.put("/api/games/valorant/settings/val.controls.key_ping", json={"value": "G"})
    hist3 = client.get("/api/games/valorant/history").json()
    key_batch = hist3[0]["batchId"]
    restage_key = client.post(f"/api/history/{key_batch}/restage").json()
    assert restage_key["stagedCount"] == 0
    assert restage_key["alreadyAlignedItems"][0]["settingId"] == "val.controls.key_ping"

    # When changed away, keybind still stays in manualConsiderations (not fake AI proposal)
    client.put("/api/games/valorant/settings/val.controls.key_ping", json={"value": "Z"})
    restage_key2 = client.post(f"/api/history/{key_batch}/restage").json()
    assert restage_key2["stagedCount"] == 0
    assert restage_key2["manualConsiderations"][0]["settingId"] == "val.controls.key_ping"


def test_relevant_already_aligned_settings_and_proportional_scope(client, services):
    set_condition(services, "adaptive", aiMode="fallback")
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "well_configured_competitive", "full", backup=False)
    set_condition(services, "adaptive", aiMode="fallback")

    # In well_configured_competitive, VSync is already Off: narrow request must NOT stage fake Off->Off change
    run = client.post("/api/chat", json={"game": "valorant", "message": "Should I turn off VSync for lower latency?"}).json()
    st = _poll_run(client, run["runId"])
    res = st["result"]
    assert res["recommendations"] == []
    assert res.get("stagedProposalId") is None
    assert res["plan"]["alreadyAlignedItems"]

    # Comprehensive setup on fresh install surfaces both actionable changes AND aligned/manual items
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "fresh_install_comprehensive", "full", backup=False)
    set_condition(services, "adaptive", aiMode="fallback")
    run2 = client.post("/api/chat", json={"game": "cs2", "message": "Configure everything for competitive FPS and clarity."}).json()
    st2 = _poll_run(client, run2["runId"])
    plan = st2["result"]["plan"]
    assert len(st2["result"]["recommendations"]) >= 12
    assert len(plan["alreadyAlignedItems"]) >= 1
    assert len(plan["manualConsiderations"]) >= 1
    assert all("why" in x and "currentDisplay" in x for x in plan["alreadyAlignedItems"])


def test_personal_setup_facts_conflicts_and_ai_only_reset_preservation(client, services):
    set_condition(services, "adaptive")
    # Save confirmed personal fact + conflicting preference/goal
    r = client.post(
        "/api/profile/personal-facts",
        json={"factKey": "push_to_talk_key", "valueText": "V", "originGame": "valorant", "sourceSettingId": "val.controls.key_team_ptt", "source": "user_explicit"},
    )
    assert r.status_code == 200
    fact_id = r.json()["id"]

    # Durable preference for visual_quality conflicts with performance goal
    client.post(
        "/api/profile/preferences",
        json={"dimension": "visual_quality", "direction": "prioritize", "scope": "durable", "source": "user_explicit", "game": "valorant"},
    )
    conn = services.store.connect()
    try:
        with conn:
            services.profile.set_session_goal(conn, "valorant", "boost FPS", ["performance"], "chat")
    finally:
        conn.close()

    prof = client.get("/api/profile").json()
    assert len(prof["personalFacts"]) == 1 and prof["personalFacts"][0]["valueText"] == "V"
    assert len(prof["conflicts"]["valorant"]) >= 1
    assert "current goal" in prof["conflicts"]["valorant"][0]["explanation"].lower()

    # ai_only reset preserves confirmed personal facts while clearing transient goals
    client.post("/api/admin/reset", json={"scenario": "default", "mode": "ai_only"})
    set_condition(services, "adaptive")
    prof2 = client.get("/api/profile").json()
    assert len(prof2["personalFacts"]) == 1
    assert prof2["sessionGoals"]["valorant"] == []

    # Deleting personal fact removes it cleanly
    assert client.delete(f"/api/profile/personal-facts/{fact_id}").status_code == 200
    assert client.get("/api/profile").json()["personalFacts"] == []


def test_four_trigger_discover_adaptive_onboarding_and_followups(client, services):
    # Scenario 1: Confirmed VALORANT personal facts -> CS2 Discover shows inspect checks referencing exact V PTT & 0.35 sens
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "valorant_onboarding_to_cs2", "full", backup=False)
    set_condition(services, "adaptive")
    s1 = client.get("/api/games/cs2/relevant-now").json()
    assert s1["onboardingStatus"] == "active"
    assert any(c["settingId"] == "cs2.kbmouse.key_mic" and c["kind"] == "inspect" and "V" in c["why"] for c in s1["items"])
    assert any(c["settingId"] == "cs2.kbmouse.mouse_sensitivity" and c["kind"] == "inspect" and "1.11" in c["why"] for c in s1["items"])

    # Switching games back and forth does NOT wipe completed onboarding checks once marked checked
    ptt_card = next(c for c in s1["items"] if c["settingId"] == "cs2.kbmouse.key_mic")
    sens_card = next(c for c in s1["items"] if c["settingId"] == "cs2.kbmouse.mouse_sensitivity")
    client.post("/api/games/cs2/relevant-now/check", json={"checkId": ptt_card["checkId"]})
    client.post("/api/games/cs2/relevant-now/check", json={"checkId": sens_card["checkId"]})
    # Dismiss any remaining onboarding card -> onboardingStatus becomes completed/dismissed; stays done after switching games
    s1_mid = client.get("/api/games/cs2/relevant-now").json()
    for c in s1_mid["items"]:
        if c["triggerGroup"] == "onboarding" and c["state"] in ("suggested", "changed"):
            client.post("/api/games/cs2/relevant-now/dismiss", json={"settingId": c["settingId"], "reason": "Checked"})
    client.put("/api/session", json={"selectedGame": "valorant"})
    client.put("/api/session", json={"selectedGame": "cs2"})
    s1_after = client.get("/api/games/cs2/relevant-now").json()
    assert s1_after["onboardingStatus"] in ("completed", "dismissed")
    refreshed = client.post("/api/games/cs2/relevant-now/refresh").json()
    assert all(c["triggerGroup"] != "onboarding" for c in refreshed["items"])

    # User can intentionally revisit onboarding (Scenario 4)
    revisited = client.post("/api/games/cs2/relevant-now/onboarding/revisit").json()
    assert revisited["onboardingStatus"] == "active"
    assert any(c["triggerGroup"] == "onboarding" for c in revisited["items"])

    # Scenario 3: Fresh user with NO priorities/facts gets neutral personal-control checkmarks, NOT unsolicited graphics overrides
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "default", "full", backup=False)
    set_condition(services, "adaptive")
    s3 = client.get("/api/games/cs2/relevant-now").json()
    assert all(c["kind"] == "inspect" for c in s3["items"])
    assert not any(c["settingId"] in ("cs2.video.msaa", "cs2.video.vsync", "cs2.video.global_shadow_quality") for c in s3["items"])

    # Trigger D: Companion follow-up after disabling VSync in VALORANT -> suggests checking NVIDIA Reflex Low Latency
    client.put("/api/games/valorant/settings/val.video.vsync", json={"value": "off"})
    fup = client.post("/api/games/valorant/relevant-now/refresh").json()
    assert any(c["settingId"] == "val.video.nvidia_reflex" and c["triggerGroup"] == "followup" for c in fup["items"])


def test_cross_game_mappings_integrity_sensitivity_math_and_safety(client, services):
    # Every curated mapping must resolve to real catalog setting IDs in both games
    assert validate_cross_game_mappings(services.registry) == []

    # Verified 360° hipfire conversion & missing-value honesty
    ok = convert_hipfire_sensitivity("valorant", "cs2", 0.35)
    assert ok["convertible"] and abs(ok["convertedValue"] - 1.11) < 0.02 and "FOV" in " ".join(ok["caveats"])
    bad = convert_hipfire_sensitivity("valorant", "cs2", None)
    assert bad["convertible"] is False and "Need a positive source hipfire sensitivity" in bad["reason"]

    # API cross-game compare endpoint + fallback chat response never auto-propose keybinds or sensitivities
    set_condition(services, "adaptive", aiMode="fallback")
    cmp_ptt = client.get("/api/cross-game/compare", params={"game": "cs2", "q": "What is the CS2 equivalent of VALORANT push to talk?"}).json()
    assert cmp_ptt["matched"] and cmp_ptt["comparisons"][0]["id"] == "push_to_talk"
    assert cmp_ptt["comparisons"][0]["proposable"] is False

    run = client.post(
        "/api/chat",
        json={"game": "cs2", "message": "How should I transfer my 0.35 VALORANT sensitivity to CS2?"},
    ).json()
    st = _poll_run(client, run["runId"])
    res = st["result"]
    assert res["recommendations"] == []  # sensitivity is NEVER staged/proposed
    assert res["crossGameComparisons"][0]["sensitivityConversion"]["convertedValue"] == 1.11
    assert res["navigateTo"]["settingId"] == "cs2.kbmouse.mouse_sensitivity"

    run_ab = client.post(
        "/api/chat",
        json={"game": "cs2", "message": "What CS2 controls are similar to VALORANT abilities and grenades?"},
    ).json()
    st_ab = _poll_run(client, run_ab["runId"])
    assert st_ab["result"]["recommendations"] == []
    assert st_ab["result"]["crossGameComparisons"][0]["relationship"] == "loose_analogy"

    # Baseline gate check on new endpoints
    set_condition(services, "baseline")
    assert client.post("/api/profile/personal-facts", json={"factKey": "ping_key", "valueText": "Z"}).status_code == 409
    assert client.post("/api/games/cs2/relevant-now/onboarding/revisit").status_code == 409
