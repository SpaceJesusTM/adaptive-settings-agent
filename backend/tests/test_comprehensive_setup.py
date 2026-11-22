"""Addendum acceptance tests: scope-aware planning, full-game setup, auto-staging & safety."""
from __future__ import annotations

import asyncio
import time

import pytest
from langchain_core.messages import AIMessage

from app.domain.scenarios import reset

from .conftest import FakeChatModel, set_condition


def snapshot(services, game):
    conn = services.store.connect()
    try:
        return services.store.flat_values(conn, game)
    finally:
        conn.close()


async def _run_turn(services, game, message, *, scope_override=None):
    started = await services.runner.start(
        game,
        message,
        {"path": "Video > Graphics Quality"},
        scope_override=scope_override,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status = services.runner.status(started["runId"])
        if status["status"] != "running":
            return status
        await asyncio.sleep(0.02)
    raise AssertionError("run did not finish")


def test_explain_and_single_setting_focused_asks_stay_narrow(services, client):
    set_condition(services, "adaptive", aiMode="fallback")

    # 1a. Pure explanation: no recs, even if scope_override="comprehensive", and zero proposals auto-staged
    res_exp = asyncio.run(
        _run_turn(services, "valorant", "What does anti-aliasing do?", scope_override="comprehensive")
    )["result"]
    assert res_exp["intent"] == "explain"
    assert res_exp["recommendations"] == []
    assert res_exp.get("stagedProposalId") is None
    assert client.get("/api/games/valorant/proposals").json() == []

    # 1b. Single-setting question ("Should I turn off VSync?"): 0-1 recommendation, never a 20-item dump
    before = snapshot(services, "valorant")
    res_vsync = asyncio.run(_run_turn(services, "valorant", "Should I turn off VSync?"))["result"]
    assert res_vsync["plan"]["scope"] == "focused"
    assert res_vsync["plan"]["singleSettingHint"] is True
    assert len(res_vsync["recommendations"]) == 1
    assert res_vsync["recommendations"][0]["settingId"] == "val.video.vsync"
    assert res_vsync["recommendations"][0]["proposedValue"] == "off"
    assert res_vsync["stagedCount"] == 1
    assert snapshot(services, "valorant") == before  # auto-stage never modifies values


def test_category_optimization_breaks_three_item_cap(services, client):
    set_condition(services, "adaptive", aiMode="fallback")
    res = asyncio.run(_run_turn(services, "cs2", "I'm getting frame drops and want smoother FPS in CS2."))["result"]
    assert res["plan"]["scope"] == "category_optimization"
    assert len(res["recommendations"]) >= 4
    pid = res["stagedProposalId"]
    assert pid
    prop = client.get(f"/api/proposals/{pid}").json()
    assert prop["autoStaged"] is True
    assert len(prop["items"]) == len(res["recommendations"])


def test_full_game_setup_exceeds_old_caps_and_applies_safely(services, client):
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "fresh_install_comprehensive", "full", backup=False)
    set_condition(services, "adaptive", aiMode="fallback")

    for game in ("valorant", "cs2"):
        before = snapshot(services, game)
        prompt = f"I just installed {game.upper()}; configure everything for competitive FPS and clarity."
        run = asyncio.run(_run_turn(services, game, prompt))
        res = run["result"]
        assert res["plan"]["scope"] == "full_game_setup"
        recs = res["recommendations"]
        assert len(recs) >= 12, f"{game} only produced {len(recs)} recs"
        cats = {r["settingId"].split(".")[1] for r in recs}
        assert len(cats) >= 3, f"{game} recs spanned only {cats}"
        assert res["plan"]["coverage"]["evaluatedCount"] > 100
        assert res["plan"]["manualConsiderations"], "should surface personal settings to consider manually"
        assert snapshot(services, game) == before  # nothing changed before approval

        pid = res["stagedProposalId"]
        assert pid
        prop = client.get(f"/api/proposals/{pid}").json()
        assert len(prop["items"]) == len(recs)
        item_ids = [it["id"] for it in prop["items"] if it["status"] == "pending"]
        assert len(item_ids) >= 12

        # Apply the entire >8-item proposal and then undo it
        applied = client.post(
            f"/api/proposals/{pid}/apply",
            json={"itemIds": item_ids, "idempotencyKey": f"apply-{game}-all"},
        )
        assert applied.status_code == 200, applied.text
        batch = applied.json()["batch"]
        assert len(batch["events"]) == len(item_ids)
        after_apply = snapshot(services, game)
        assert after_apply != before

        # Replay idempotency key does not double-apply
        replay = client.post(
            f"/api/proposals/{pid}/apply",
            json={"itemIds": item_ids, "idempotencyKey": f"apply-{game}-all"},
        )
        assert replay.status_code == 200
        assert replay.json()["idempotentReplay"] is True

        # Undo restores every setting cleanly
        undone = client.post(f"/api/history/{batch['batchId']}/undo", json={})
        assert undone.status_code == 200
        assert snapshot(services, game) == before


def test_well_configured_scenario_has_zero_forced_changes(services, client):
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "well_configured_competitive", "full", backup=False)
    set_condition(services, "adaptive", aiMode="fallback")

    for game in ("valorant", "cs2"):
        res = asyncio.run(
            _run_turn(services, game, f"I just installed {game.upper()}; configure everything for competitive FPS and clarity.")
        )["result"]
        assert res["recommendations"] == []
        assert res["plan"]["coverage"]["alreadyAlignedCount"] >= 20
        assert res.get("stagedProposalId") is None
        assert client.get(f"/api/games/{game}/proposals").json() == []


def test_auto_stage_idempotence_and_cancellation_safety(services, fake_model_holder, connected_ollama):
    set_condition(services, "adaptive", aiMode="local")
    before = snapshot(services, "valorant")

    # Test cancellation never creates a proposal
    fake_model_holder["model"] = FakeChatModel(delay_s=3.0)

    async def cancel_flow():
        st = await services.runner.start("valorant", "Configure everything for competitive FPS", {})
        await asyncio.sleep(0.05)
        return await services.runner.cancel(st["runId"])

    cancelled = asyncio.run(cancel_flow())
    assert cancelled["status"] == "cancelled"
    assert snapshot(services, "valorant") == before
    assert services.proposals.list("valorant") == []

    # Calling auto_stage_for_run multiple times with same run_id is strictly idempotent
    conn = services.store.connect()
    try:
        from app.domain.db import write_tx

        items = [{"settingId": "val.video.bloom", "proposedValue": "off", "why": "Test"}]
        with write_tx(conn):
            first = services.proposals.auto_stage_for_run(conn, "valorant", source="ai", run_id="run_dup_1", title="T", items=items)
            second = services.proposals.auto_stage_for_run(conn, "valorant", source="ai", run_id="run_dup_1", title="T", items=items)
        assert first["proposalId"] == second["proposalId"]
        assert second["idempotentReplay"] is True
        assert len(services.proposals.list("valorant")) == 1
    finally:
        conn.close()


def test_supplement_followup_does_not_repeat_staged_settings(services, client):
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "fresh_install_comprehensive", "full", backup=False)
    set_condition(services, "adaptive", aiMode="fallback")

    # Run a category ask first (stages Video settings)
    first = asyncio.run(_run_turn(services, "cs2", "Help reduce input lag.", scope_override="focused"))["result"]
    first_ids = {r["settingId"] for r in first["recommendations"]}
    assert first_ids

    # Follow up asking what else to improve
    second = asyncio.run(_run_turn(services, "cs2", "What else could I improve? Include minor tweaks."))["result"]
    second_ids = {r["settingId"] for r in second["recommendations"]}
    assert second["plan"]["scope"] == "full_game_setup"
    assert second["plan"]["isSupplement"] is True
    assert not (first_ids & second_ids), "supplement must not duplicate already-staged settings"


def test_safety_filters_enforce_personal_controls_even_in_large_plans(services):
    from app.agent.schemas import AssistantDraft, DraftRecommendation
    from app.agent.scope import ScopePlan
    from app.agent.validate import validate_draft

    wide = ScopePlan(
        scope="full_game_setup",
        max_recs=40,
        auto_stage=True,
        include_minor=True,
        is_supplement=False,
        reason="test",
        inferred_dimensions=["performance"],
    )
    draft = AssistantDraft(
        intent="recommend",
        reply="Checked everything.",
        recommendations=[
            DraftRecommendation(setting_id="cs2.crosshair.xhair_color_hex", proposed_value="#FF0000", why_for_goal="color", confidence="low"),
            DraftRecommendation(setting_id="cs2.kbmouse.key_forward", proposed_value="E", why_for_goal="keybind", confidence="low"),
            DraftRecommendation(setting_id="cs2.kbmouse.mouse_sensitivity", proposed_value="2.0", why_for_goal="sens", confidence="low"),
            DraftRecommendation(setting_id="cs2.video.video_preset", proposed_value="0", why_for_goal="preset", confidence="low"),
            DraftRecommendation(setting_id="cs2.video.vsync", proposed_value="0", why_for_goal="latency", confidence="high"),
        ],
    )
    v = validate_draft(services.store, "cs2", draft, source="ai", max_recommendations=wide.max_recs, scope_plan=wide)
    assert [r["settingId"] for r in v["recommendations"]] == ["cs2.video.vsync"]
    rejected = {f["settingId"]: f["kind"] for f in v["filtered"]}
    assert rejected["cs2.crosshair.xhair_color_hex"] == "not_proposable"
    assert rejected["cs2.kbmouse.key_forward"] == "not_proposable"
    assert rejected["cs2.kbmouse.mouse_sensitivity"] == "not_proposable"
    assert rejected["cs2.video.video_preset"] == "not_proposable"


def test_multi_batch_compose_and_partial_coverage_handling(services, fake_model_holder, connected_ollama):
    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir, "fresh_install_comprehensive", "full", backup=False)
    set_condition(services, "adaptive", aiMode="local")
    # Provide batch 1 valid payload, then intentionally invalid JSON on batch 2 -> partialCoverage=True without losing batch 1
    fake_model_holder["model"] = FakeChatModel(
        plan_responses=[AIMessage(content="READY")],
        compose_payloads=[
            {
                "intent": "recommend",
                "reply": "Prepared Video optimizations first.",
                "goal_dimensions": ["performance"],
                "recommendations": [
                    {"setting_id": "cs2.video.vsync", "proposed_value": "Disabled", "why_for_goal": "Lower input delay.", "confidence": "high"},
                    {"setting_id": "cs2.video.msaa", "proposed_value": "2x MSAA", "why_for_goal": "Less GPU cost.", "confidence": "medium"},
                ],
            },
            "not valid json for batch 2",
        ],
    )
    run = asyncio.run(_run_turn(services, "cs2", "I just installed CS2; configure everything for competitive FPS and clarity."))
    assert run["status"] == "succeeded"
    res = run["result"]
    assert res["plan"]["partialCoverage"] is True
    assert len(res["recommendations"]) == 2
    assert any("Partial coverage" in n for n in res["validationNotes"])
